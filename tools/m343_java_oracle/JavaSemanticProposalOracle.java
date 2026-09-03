import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.tree.TypeParameterTree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.SourcePositions;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;
import java.nio.charset.StandardCharsets;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.lang.model.element.Element;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.Modifier;
import javax.lang.model.element.ModuleElement;
import javax.lang.model.element.PackageElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.element.TypeParameterElement;
import javax.lang.model.type.ArrayType;
import javax.lang.model.type.DeclaredType;
import javax.lang.model.type.TypeKind;
import javax.lang.model.type.TypeMirror;
import javax.lang.model.util.Elements;
import javax.lang.model.util.Types;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

/** Independent semantic proposal oracle. No production or Tree-sitter dependency. */
public final class JavaSemanticProposalOracle {
    private static final String VERSION = "m343.javac-semantic-proposal-oracle.v1";
    private static final PrintWriter OUT = new PrintWriter(
        new OutputStreamWriter(System.out, StandardCharsets.UTF_8), true);

    private JavaSemanticProposalOracle() {}

    public static void main(String[] args) throws Exception {
        if (args.length < 2 || !args[0].equals("oracle")) {
            throw new IllegalArgumentException("usage: oracle ROOT SOURCE...");
        }
        Path root = Path.of(args[1]).toAbsolutePath().normalize();
        List<Path> paths = new ArrayList<>();
        for (int i = 2; i < args.length; i++) paths.add(Path.of(args[i]));
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("JDK compiler unavailable");
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        try (StandardJavaFileManager files = compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            Iterable<? extends JavaFileObject> inputs = files.getJavaFileObjectsFromPaths(paths);
            List<String> options = new ArrayList<>(List.of(
                "--release", "21", "-proc:none", "-Xlint:none", "-Xmaxerrs", "10000"));
            String patchModuleRoot = System.getProperty("m344.patchJavaBase");
            if (patchModuleRoot != null && !patchModuleRoot.isBlank()) {
                options.add("--patch-module");
                options.add("java.base=" + patchModuleRoot);
            }
            JavacTask task = (JavacTask) compiler.getTask(
                null, files, diagnostics, options, null, inputs);
            List<CompilationUnitTree> units = new ArrayList<>();
            task.parse().forEach(units::add);
            try { task.analyze(); } catch (RuntimeException ignored) { /* diagnostics are truth */ }
            Trees trees = Trees.instance(task);
            SourcePositions positions = trees.getSourcePositions();
            Types types = task.getTypes();
            Elements elements = task.getElements();
            for (CompilationUnitTree unit : units) {
                new Scanner(root, unit, trees, positions, types, elements).scan(unit, null);
            }
            diagnostics.getDiagnostics().stream()
                .filter(item -> item.getKind() == Diagnostic.Kind.ERROR)
                .sorted(Comparator.comparing(
                        (Diagnostic<? extends JavaFileObject> item) ->
                            sourceUnit(root, item.getSource()))
                    .thenComparingLong(item -> item.getStartPosition())
                    .thenComparing(item -> item.getCode()))
                .forEach(item -> OUT.println(diagnosticJson(root, item)));
        }
    }

    private static final class Scanner extends TreePathScanner<Void, Void> {
        private final Path root;
        private final CompilationUnitTree unit;
        private final Trees trees;
        private final SourcePositions positions;
        private final Types types;
        private final Elements elements;
        private final ArrayDeque<String> typePath = new ArrayDeque<>();
        private final String text;
        private final byte[] bytes;
        private final String documentHash;
        private final String sourceUnit;

        Scanner(Path root, CompilationUnitTree unit, Trees trees,
                SourcePositions positions, Types types, Elements elements) throws Exception {
            this.root = root;
            this.unit = unit;
            this.trees = trees;
            this.positions = positions;
            this.types = types;
            this.elements = elements;
            Path path = Path.of(unit.getSourceFile().toUri()).toAbsolutePath().normalize();
            this.bytes = Files.readAllBytes(path);
            this.text = new String(bytes, StandardCharsets.UTF_8);
            this.documentHash = sha256(bytes);
            this.sourceUnit = root.relativize(path).toString().replace('\\', '/');
        }

        @Override public Void visitClass(com.sun.source.tree.ClassTree tree, Void unused) {
            typePath.addLast(tree.getSimpleName().toString());
            super.visitClass(tree, unused);
            typePath.removeLast();
            return null;
        }

        @Override public Void visitMethod(MethodTree tree, Void unused) {
            if (typePath.isEmpty()) return super.visitMethod(tree, unused);
            long charStart = positions.getStartPosition(unit, tree);
            long charEnd = positions.getEndPosition(unit, tree);
            if (charStart < 0 || charEnd < charStart) return super.visitMethod(tree, unused);
            int start = utf8Offset((int) charStart);
            int end = utf8Offset((int) charEnd);
            boolean constructor = tree.getReturnType() == null;
            Element rawElement = trees.getElement(getCurrentPath());
            ExecutableElement executable = rawElement instanceof ExecutableElement value ? value : null;
            String memberName = constructor ? typePath.getLast() : tree.getName().toString();
            List<String> sourceParameters = new ArrayList<>();
            List<String> parameterNames = new ArrayList<>();
            List<Boolean> varargs = new ArrayList<>();
            List<Integer> parameterDimensions = new ArrayList<>();
            for (int index = 0; index < tree.getParameters().size(); index++) {
                VariableTree parameter = tree.getParameters().get(index);
                String source = canonicalSourceType(parameter.getType().toString());
                boolean spread = executable != null && executable.isVarArgs()
                    && index == tree.getParameters().size() - 1;
                if (spread) source = source.replaceFirst("\\[\\]$", "...");
                sourceParameters.add(source);
                parameterNames.add(parameter.getName().toString());
                varargs.add(spread);
                parameterDimensions.add(arrayDimensions(source));
            }
            List<String> resolvedParameters = new ArrayList<>();
            if (executable != null) for (var parameter : executable.getParameters()) {
                resolvedParameters.add(resolvedType(parameter.asType()));
            }
            String sourceReturn = constructor ? "void" : canonicalSourceType(tree.getReturnType().toString());
            String resolvedReturn = executable == null ? null : resolvedType(executable.getReturnType());
            List<String> typeParameters = new ArrayList<>();
            List<List<String>> bounds = new ArrayList<>();
            List<List<String>> resolutionSourceBounds = new ArrayList<>();
            List<List<String>> resolvedAllBounds = new ArrayList<>();
            List<String> erasures = new ArrayList<>();
            for (int index = 0; index < tree.getTypeParameters().size(); index++) {
                TypeParameterTree sourceParameter = tree.getTypeParameters().get(index);
                typeParameters.add(sourceParameter.getName().toString());
                List<String> sourceBounds = sourceParameter.getBounds().stream()
                    .map(Object::toString).map(JavaSemanticProposalOracle::canonicalSourceType).toList();
                bounds.add(sourceBounds);
                resolutionSourceBounds.add(sourceBounds.isEmpty() ? List.of("Object") : sourceBounds);
                if (executable != null && index < executable.getTypeParameters().size()) {
                    TypeParameterElement element = executable.getTypeParameters().get(index);
                    resolvedAllBounds.add(element.getBounds().stream().map(this::resolvedType).toList());
                    erasures.add(element.getBounds().isEmpty()
                        ? "java.lang.Object" : resolvedType(types.erasure(element.getBounds().get(0))));
                } else {
                    resolvedAllBounds.add(List.of());
                    erasures.add(null);
                }
            }
            List<String> sourceExceptions = tree.getThrows().stream()
                .map(Object::toString).map(JavaSemanticProposalOracle::canonicalSourceType).toList();
            List<String> resolvedExceptions = new ArrayList<>();
            if (executable != null) for (TypeMirror value : executable.getThrownTypes()) {
                resolvedExceptions.add(resolvedType(value));
            }
            TypeElement owner = executable != null && executable.getEnclosingElement() instanceof TypeElement value
                ? value : null;
            String receiver = owner == null ? receiverFromSyntax() : owner.getQualifiedName().toString();
            String receiverBinary = owner == null ? receiver : elements.getBinaryName(owner).toString();
            String descriptor = executable == null ? null : descriptor(executable, constructor);
            boolean supported = executable != null
                && descriptor != null
                && resolvedParameters.stream().noneMatch(value -> value == null)
                && resolvedReturn != null
                && erasures.stream().noneMatch(value -> value == null)
                && resolvedExceptions.stream().noneMatch(value -> value == null);
            String accessibility = accessibility(tree.getModifiers().getFlags());
            String enclosingAccessibility = owner == null ? "PUBLIC" : enclosingAccessibility(owner);
            ModuleElement module = owner == null ? null : elements.getModuleOf(owner);
            PackageElement packageElement = owner == null ? null : elements.getPackageOf(owner);
            String moduleName = module == null || module.isUnnamed() ? null : module.getQualifiedName().toString();
            boolean exported = module == null || module.isUnnamed() || packageElement == null
                || module.getDirectives().stream().anyMatch(directive ->
                    directive.getKind() == ModuleElement.DirectiveKind.EXPORTS
                    && ((ModuleElement.ExportsDirective) directive).getPackage().equals(packageElement));
            List<String> modifiers = tree.getModifiers().getFlags().stream()
                .map(value -> value.name().toLowerCase(Locale.ROOT)).sorted().toList();
            String deprecatedSince = deprecatedSince(tree);
            List<String> nesting = new ArrayList<>(typePath);
            String top = nesting.remove(0);
            String row = "{" +
                json("record_type", "proposal") + "," + json("oracle_version", VERSION) + "," +
                json("source_unit_id", sourceUnit) + "," + json("document_bytes_hash", documentHash) + "," +
                number("start_offset", start) + "," + number("end_offset", end) + "," +
                number("start_line", unit.getLineMap().getLineNumber(charStart)) + "," +
                number("end_line", unit.getLineMap().getLineNumber(Math.max(charStart, charEnd - 1))) + "," +
                nullable("package_name", unit.getPackageName() == null ? null : unit.getPackageName().toString()) + "," +
                json("top_level_type_name", top) + "," + array("nested_type_path", nesting) + "," +
                json("member_kind", constructor ? "constructor" : "method") + "," + json("member_name", memberName) + "," +
                json("canonical_source_signature", sourceSignature(tree, executable, constructor)) + "," +
                nullable("erased_jvm_descriptor", descriptor) + "," +
                json("receiver_source_identity", receiver) + "," + json("receiver_binary_identity", receiverBinary) + "," +
                array("parameter_names", parameterNames) + "," + array("source_parameter_types", sourceParameters) + "," +
                nullableArray("resolved_parameter_types", resolvedParameters) + "," + boolArray("parameter_varargs", varargs) + "," +
                intArray("parameter_array_dimensions", parameterDimensions) + "," + json("source_return_type", sourceReturn) + "," +
                nullable("resolved_return_type", resolvedReturn) + "," + number("return_array_dimensions", arrayDimensions(sourceReturn)) + "," +
                array("method_type_parameters", typeParameters) + "," + nestedArray("intersection_bounds", bounds) + "," +
                nestedArray("resolution_source_bounds", resolutionSourceBounds) + "," +
                nullableNestedArray("resolved_intersection_bounds", resolvedAllBounds) + "," +
                nullableArray("first_bound_erasures", erasures) + "," + array("declared_exception_source_types", sourceExceptions) + "," +
                nullableArray("resolved_declared_exception_types", resolvedExceptions) + "," + array("modifiers", modifiers) + "," +
                json("accessibility", accessibility) + "," + json("enclosing_type_accessibility", enclosingAccessibility) + "," +
                nullable("module_name", moduleName) + "," + bool("package_exported", exported) + "," +
                nullable("deprecated_since", deprecatedSince) + "," +
                bool("expected_supported", supported) +
                "}";
            OUT.println(row);
            return super.visitMethod(tree, unused);
        }

        private String receiverFromSyntax() {
            String packageName = unit.getPackageName() == null ? "" : unit.getPackageName().toString() + ".";
            return packageName + String.join(".", typePath);
        }
        private String deprecatedSince(MethodTree tree) {
            Pattern pattern = Pattern.compile(
                "@(?:java\\.lang\\.)?Deprecated\\s*\\([^)]*\\bsince\\s*=\\s*\\\"([^\\\"]*)\\\"");
            for (var annotation : tree.getModifiers().getAnnotations()) {
                Matcher matcher = pattern.matcher(annotation.toString());
                if (matcher.find()) return matcher.group(1);
            }
            return null;
        }
        private int utf8Offset(int chars) {
            return text.substring(0, chars).getBytes(StandardCharsets.UTF_8).length;
        }
        private String descriptor(ExecutableElement method, boolean constructor) {
            StringBuilder result = new StringBuilder(constructor ? "<init>(" : method.getSimpleName() + "(");
            for (var parameter : method.getParameters()) {
                String value = typeDescriptor(types.erasure(parameter.asType()));
                if (value == null) return null;
                result.append(value);
            }
            result.append(')');
            String returns = constructor ? "V" : typeDescriptor(types.erasure(method.getReturnType()));
            return returns == null ? null : result.append(returns).toString();
        }
        private String typeDescriptor(TypeMirror type) {
            return switch (type.getKind()) {
                case BOOLEAN -> "Z"; case BYTE -> "B"; case CHAR -> "C"; case DOUBLE -> "D";
                case FLOAT -> "F"; case INT -> "I"; case LONG -> "J"; case SHORT -> "S"; case VOID -> "V";
                case ARRAY -> { String value = typeDescriptor(((ArrayType) type).getComponentType()); yield value == null ? null : "[" + value; }
                case DECLARED -> { Element item = ((DeclaredType) type).asElement(); yield item instanceof TypeElement declared
                    ? "L" + elements.getBinaryName(declared).toString().replace('.', '/') + ";" : null; }
                default -> null;
            };
        }
        private String resolvedType(TypeMirror type) {
            if (containsError(type)) return null;
            if (type.getKind() == TypeKind.ARRAY) return resolvedType(((ArrayType) type).getComponentType()) + "[]";
            if (type.getKind().isPrimitive() || type.getKind() == TypeKind.VOID) return type.toString();
            TypeMirror erased = types.erasure(type);
            if (erased.getKind() == TypeKind.DECLARED) {
                Element item = ((DeclaredType) erased).asElement();
                if (item instanceof TypeElement declared) return declared.getQualifiedName().toString();
            }
            return null;
        }
        private boolean containsError(TypeMirror type) {
            if (type == null || type.getKind() == TypeKind.ERROR) return true;
            return type.getKind() == TypeKind.ARRAY && containsError(((ArrayType) type).getComponentType());
        }
        private String sourceSignature(MethodTree tree, ExecutableElement element, boolean constructor) {
            List<String> parameters = new ArrayList<>();
            for (VariableTree parameter : tree.getParameters()) {
                parameters.add(canonicalSourceType(parameter.getType().toString()));
            }
            if (element != null && element.isVarArgs() && !parameters.isEmpty()) {
                int last = parameters.size() - 1;
                parameters.set(last, parameters.get(last).replaceFirst("\\[\\]$", "..."));
            }
            return (constructor ? "<init>" : tree.getName().toString()) + "(" +
                String.join(",", parameters) + "):" + (constructor ? "void" : canonicalSourceType(tree.getReturnType().toString()));
        }
    }

    private static String canonicalSourceType(String value) {
        return value.trim().replaceAll(",\\s+", ",");
    }

    private static String diagnosticJson(Path root, Diagnostic<? extends JavaFileObject> item) {
        String unit = sourceUnit(root, item.getSource());
        Path path = item.getSource() == null ? null : Path.of(item.getSource().toUri());
        int start = byteOffset(path, item.getStartPosition());
        int end = byteOffset(path, item.getEndPosition());
        return "{" + json("record_type", "diagnostic") + "," + json("diagnostic_code", item.getCode()) + "," +
            json("diagnostic_kind", item.getKind().name()) + "," + json("source_unit_id", unit) + "," +
            number("start_offset", start) + "," + number("end_offset", end) + "," +
            number("line", item.getLineNumber()) + "," + number("column", item.getColumnNumber()) + "," +
            json("normalized_category", category(item.getCode())) + "}";
    }
    private static String category(String code) {
        String value = code.toLowerCase(Locale.ROOT);
        if (value.contains("ambiguous")) return "AMBIGUOUS_TYPE";
        if (value.contains("not.def.access") || value.contains("report.access")) return "INACCESSIBLE_TYPE";
        if (value.contains("package.not.visible")) return "NON_EXPORTED_MODULE_PACKAGE";
        if (value.contains("doesnt.exist") || value.contains("does.not.exist")) return "INVALID_IMPORT";
        if (value.contains("bound") || value.contains("type.var")) return "INVALID_TYPE_VARIABLE_BOUND";
        if (value.contains("throws")) return "INVALID_THROWS_TYPE";
        if (value.contains("already.defined") || value.contains("name.clash")) return "DUPLICATE_SIGNATURE";
        if (value.contains("expected") || value.contains("illegal.start")) return "MALFORMED_GENERIC_DECLARATION";
        if (value.contains("encl") || value.contains("receiver")) return "INVALID_RECEIVER_OR_ENCLOSING_TYPE";
        if (value.contains("cant.resolve")) return "UNRESOLVED_TYPE";
        return "COMPILER_ERROR";
    }
    private static String sourceUnit(Path root, JavaFileObject source) {
        if (source == null) return "<none>";
        Path path = Path.of(source.toUri()).toAbsolutePath().normalize();
        return root.relativize(path).toString().replace('\\', '/');
    }
    private static int byteOffset(Path path, long chars) {
        if (path == null || chars < 0) return -1;
        try {
            String text = Files.readString(path, StandardCharsets.UTF_8);
            return text.substring(0, Math.min((int) chars, text.length())).getBytes(StandardCharsets.UTF_8).length;
        } catch (Exception error) { return -1; }
    }
    private static String accessibility(Set<Modifier> values) {
        if (values.contains(Modifier.PUBLIC)) return "PUBLIC";
        if (values.contains(Modifier.PROTECTED)) return "PROTECTED";
        if (values.contains(Modifier.PRIVATE)) return "PRIVATE";
        return "PACKAGE";
    }
    private static String enclosingAccessibility(TypeElement owner) {
        String result = "PUBLIC";
        Element current = owner;
        while (current instanceof TypeElement value) {
            String access = accessibility(value.getModifiers());
            if (access.equals("PRIVATE")) return access;
            if (access.equals("PACKAGE")) result = access;
            current = value.getEnclosingElement();
        }
        return result;
    }
    private static int arrayDimensions(String value) {
        int dimensions = value.endsWith("...") ? 1 : 0;
        String text = value.endsWith("...") ? value.substring(0, value.length() - 3) : value;
        while (text.endsWith("[]")) { dimensions++; text = text.substring(0, text.length() - 2); }
        return dimensions;
    }
    private static String sha256(byte[] value) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
    }
    private static String escape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"")
            .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t");
    }
    private static String json(String key, String value) { return "\"" + key + "\":\"" + escape(value) + "\""; }
    private static String nullable(String key, String value) { return value == null ? "\"" + key + "\":null" : json(key, value); }
    private static String number(String key, long value) { return "\"" + key + "\":" + value; }
    private static String bool(String key, boolean value) { return "\"" + key + "\":" + value; }
    private static String array(String key, List<String> values) {
        return "\"" + key + "\":[" + String.join(",", values.stream().map(value -> "\"" + escape(value) + "\"").toList()) + "]";
    }
    private static String nullableArray(String key, List<String> values) {
        return "\"" + key + "\":[" + String.join(",", values.stream().map(value -> value == null ? "null" : "\"" + escape(value) + "\"").toList()) + "]";
    }
    private static String boolArray(String key, List<Boolean> values) {
        return "\"" + key + "\":[" + String.join(",", values.stream().map(Object::toString).toList()) + "]";
    }
    private static String intArray(String key, List<Integer> values) {
        return "\"" + key + "\":[" + String.join(",", values.stream().map(Object::toString).toList()) + "]";
    }
    private static String nestedArray(String key, List<List<String>> values) {
        return "\"" + key + "\":[" + String.join(",", values.stream().map(value ->
            "[" + String.join(",", value.stream().map(item -> "\"" + escape(item) + "\"").toList()) + "]").toList()) + "]";
    }
    private static String nullableNestedArray(String key, List<List<String>> values) {
        return "\"" + key + "\":[" + String.join(",", values.stream().map(value ->
            "[" + String.join(",", value.stream().map(item -> item == null ? "null" : "\"" + escape(item) + "\"").toList()) + "]").toList()) + "]";
    }
}
