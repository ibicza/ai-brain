import com.sun.source.tree.ClassTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.SourcePositions;
import com.sun.source.util.TreePath;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import javax.lang.model.element.Element;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.type.ArrayType;
import javax.lang.model.type.DeclaredType;
import javax.lang.model.type.TypeKind;
import javax.lang.model.type.TypeMirror;
import javax.lang.model.util.Elements;
import javax.lang.model.util.Types;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

/** Independent JDK 21 compiler oracle. It has no production or Tree-sitter dependency. */
public final class JavaSemanticOracle {
    private static final String VERSION = "m342.javac-oracle.v1";

    private JavaSemanticOracle() {}

    public static void main(String[] args) throws Exception {
        if (args.length < 2 || !(args[0].equals("census") || args[0].equals("oracle"))) {
            throw new IllegalArgumentException("usage: census|oracle SOURCE...");
        }
        boolean classify = args[0].equals("oracle");
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("JDK compiler unavailable");
        List<Path> paths = new ArrayList<>();
        for (int i = 1; i < args.length; i++) paths.add(Path.of(args[i]));
        try (StandardJavaFileManager files = compiler.getStandardFileManager(null, null, StandardCharsets.UTF_8)) {
            Iterable<? extends JavaFileObject> inputs = files.getJavaFileObjectsFromPaths(paths);
            List<String> options = List.of("--release", "21", "-proc:none", "-Xlint:none");
            JavacTask task = (JavacTask) compiler.getTask(null, files, diagnostic -> {}, options, null, inputs);
            List<CompilationUnitTree> units = new ArrayList<>();
            task.parse().forEach(units::add);
            if (classify) {
                try { task.analyze(); } catch (RuntimeException ignored) { /* erroneous inputs are labelled */ }
            }
            Trees trees = Trees.instance(task);
            SourcePositions positions = trees.getSourcePositions();
            Types types = task.getTypes();
            Elements elements = task.getElements();
            for (CompilationUnitTree unit : units) {
                new Scanner(unit, trees, positions, types, elements, classify).scan(unit, null);
            }
        }
    }

    private static final class Scanner extends TreePathScanner<Void, Void> {
        private final CompilationUnitTree unit;
        private final Trees trees;
        private final SourcePositions positions;
        private final Types types;
        private final Elements elements;
        private final boolean classify;
        private final ArrayDeque<String> typesPath = new ArrayDeque<>();
        private final String text;
        private final byte[] bytes;
        private final String documentHash;

        Scanner(CompilationUnitTree unit, Trees trees, SourcePositions positions, Types types,
                Elements elements, boolean classify) throws Exception {
            this.unit = unit;
            this.trees = trees;
            this.positions = positions;
            this.types = types;
            this.elements = elements;
            this.classify = classify;
            Path path = Path.of(unit.getSourceFile().toUri());
            this.bytes = Files.readAllBytes(path);
            this.text = new String(bytes, StandardCharsets.UTF_8);
            this.documentHash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        }

        @Override public Void visitClass(ClassTree tree, Void unused) {
            typesPath.addLast(tree.getSimpleName().toString());
            super.visitClass(tree, unused);
            typesPath.removeLast();
            return null;
        }

        @Override public Void visitMethod(MethodTree tree, Void unused) {
            if (typesPath.isEmpty()) return super.visitMethod(tree, unused);
            long charStart = positions.getStartPosition(unit, tree);
            long charEnd = positions.getEndPosition(unit, tree);
            if (charStart < 0 || charEnd < charStart) return super.visitMethod(tree, unused);
            int start = utf8Offset((int) charStart);
            int end = utf8Offset((int) charEnd);
            long startLine = unit.getLineMap().getLineNumber(charStart);
            long endLine = unit.getLineMap().getLineNumber(Math.max(charStart, charEnd - 1));
            boolean constructor = tree.getReturnType() == null;
            String memberName = constructor ? typesPath.getLast() : tree.getName().toString();
            String descriptor = null;
            String unsupported = classify ? "ORACLE_ELEMENT_MISSING" : "NOT_CLASSIFIED";
            ExecutableElement executable = null;
            if (classify) {
                Element element = trees.getElement(getCurrentPath());
                if (element instanceof ExecutableElement value) executable = value;
                if (executable != null && executable.getParameters().stream().noneMatch(
                        item -> containsError(item.asType())) && !containsError(executable.getReturnType())) {
                    descriptor = descriptor(executable, constructor);
                    unsupported = descriptor == null ? "ORACLE_UNSUPPORTED_TYPE" : null;
                } else if (executable != null) {
                    unsupported = "ORACLE_ERROR_TYPE";
                }
            }
            String packageName = unit.getPackageName() == null ? null : unit.getPackageName().toString();
            List<String> nesting = new ArrayList<>(typesPath);
            String top = nesting.remove(0);
            String sourceSignature = sourceSignature(tree, executable, constructor);
            String row = "{" +
                json("oracle_version", VERSION) + "," +
                json("source_unit_id", Path.of(unit.getSourceFile().toUri()).getFileName().toString()) + "," +
                json("document_bytes_hash", documentHash) + "," +
                number("start_offset", start) + "," + number("end_offset", end) + "," +
                number("start_line", startLine) + "," + number("end_line", endLine) + "," +
                nullable("package_name", packageName) + "," + json("top_level_type_name", top) + "," +
                array("nested_type_path", nesting) + "," +
                json("member_kind", constructor ? "constructor" : "method") + "," +
                json("member_name", memberName) + "," + json("canonical_source_signature", sourceSignature) + "," +
                nullable("erased_jvm_descriptor", descriptor) + "," +
                bool("expected_supported", descriptor != null) + "," + nullable("unsupported_reason", unsupported) +
                "}";
            System.out.println(row);
            return super.visitMethod(tree, unused);
        }

        private int utf8Offset(int chars) {
            return text.substring(0, chars).getBytes(StandardCharsets.UTF_8).length;
        }

        private boolean containsError(TypeMirror type) {
            if (type.getKind() == TypeKind.ERROR) return true;
            if (type.getKind() == TypeKind.ARRAY) return containsError(((ArrayType) type).getComponentType());
            return false;
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
                case ARRAY -> {
                    String value = typeDescriptor(((ArrayType) type).getComponentType());
                    yield value == null ? null : "[" + value;
                }
                case DECLARED -> {
                    Element element = ((DeclaredType) type).asElement();
                    if (!(element instanceof TypeElement declared)) yield null;
                    yield "L" + elements.getBinaryName(declared).toString().replace('.', '/') + ";";
                }
                default -> null;
            };
        }

        private String sourceSignature(MethodTree tree, ExecutableElement element, boolean constructor) {
            List<String> parameters = new ArrayList<>();
            for (VariableTree parameter : tree.getParameters()) parameters.add(parameter.getType().toString());
            if (element != null && element.isVarArgs() && !parameters.isEmpty()) {
                int last = parameters.size() - 1;
                parameters.set(last, parameters.get(last).replaceFirst("\\[\\]$", "...") );
            }
            String name = constructor ? "<init>" : tree.getName().toString();
            String returns = constructor ? "void" : tree.getReturnType().toString();
            return name + "(" + String.join(",", parameters) + "):" + returns;
        }
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
        List<String> encoded = values.stream().map(value -> "\"" + escape(value) + "\"").toList();
        return "\"" + key + "\":[" + String.join(",", encoded) + "]";
    }
}
