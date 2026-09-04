import java.io.BufferedReader;
import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Base64;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

/** Independent, dependency-free SPDX reference used only by the M-33.6d oracle. */
public final class IndependentSpdxReference {
    private static final List<String> IDS = List.of(
        "Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause",
        "GPL-2.0-only", "Classpath-exception-2.0");

    private record Template(
        String id, byte[] canonicalBytes, String normalizedCanonical,
        Pattern interpretedPattern, List<String> apacheBases) {}

    private record Decision(String status, String licenseId, boolean automatic) {}

    private IndependentSpdxReference() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                "usage: IndependentSpdxReference SNAPSHOT INPUT_TSV IMPLEMENTATION_SHA256");
        }
        Path snapshot = Path.of(args[0]).toRealPath();
        Path input = Path.of(args[1]).toRealPath();
        String implementationHash = requireHash(args[2]);
        List<Template> templates = loadTemplates(snapshot);
        try (BufferedReader reader = Files.newBufferedReader(input, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                String[] fields = line.split("\\t", -1);
                if (fields.length != 3 || !fields[0].matches("[a-z0-9._-]+")) {
                    throw new IllegalArgumentException("malformed immutable case input");
                }
                byte[] raw = Base64.getDecoder().decode(fields[2]);
                Decision decision = decide(raw, templates);
                String normalizedHash;
                try {
                    normalizedHash = sha256(normalize(decodeStrict(raw)).getBytes(StandardCharsets.UTF_8));
                } catch (CharacterCodingException badUtf8) {
                    normalizedHash = sha256(new byte[0]);
                }
                String body = "{"
                    + json("automatic") + ":" + decision.automatic + ","
                    + json("case_id") + ":" + json(fields[0]) + ","
                    + json("match_status") + ":" + json(decision.status) + ","
                    + json("normalized_sha256") + ":" + json(normalizedHash) + ","
                    + json("reference_implementation_sha256") + ":" + json(implementationHash) + ","
                    + json("schema_version") + ":1,"
                    + json("source_document") + ":" + json(fields[1]) + ","
                    + json("source_document_sha256") + ":" + json(sha256(raw)) + ","
                    + json("template_license_id") + ":"
                    + (decision.licenseId == null ? "null" : json(decision.licenseId))
                    + "}";
                System.out.println(body.substring(0, body.length() - 1) + ","
                    + json("receipt_sha256") + ":" + json(sha256(body.getBytes(StandardCharsets.UTF_8)))
                    + "}");
            }
        }
        long peakHeapBytes = ManagementFactory.getMemoryPoolMXBeans().stream()
            .mapToLong(bean -> Math.max(0L, bean.getPeakUsage().getUsed()))
            .sum();
        System.err.println("M336D_PEAK_JAVA_HEAP_BYTES=" + peakHeapBytes);
    }

    private static List<Template> loadTemplates(Path snapshot) throws Exception {
        List<Template> result = new ArrayList<>();
        for (String id : IDS) {
            Path textPath = confined(snapshot, id + ".txt");
            Path xmlPath = confined(snapshot, id + ".xml");
            byte[] canonical = Files.readAllBytes(textPath);
            Document document = secureFactory().newDocumentBuilder().parse(xmlPath.toFile());
            Element element = firstTemplateElement(document);
            if (!id.equals(element.getAttribute("licenseId"))) {
                throw new IllegalArgumentException("SPDX XML identity mismatch: " + id);
            }
            Element text = firstChild(element, "text");
            String expression = renderChildren(text);
            Pattern pattern = Pattern.compile("^\\s*" + expression + "\\s*$",
                Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);
            String normalized = normalize(decodeStrict(canonical));
            List<String> apacheBases = id.equals("Apache-2.0")
                ? apacheBases(lexical(decodeStrict(canonical))) : List.of();
            result.add(new Template(id, canonical, normalized, pattern, apacheBases));
        }
        return List.copyOf(result);
    }

    private static Decision decide(byte[] raw, List<Template> templates) {
        String decoded;
        try {
            decoded = decodeStrict(raw);
        } catch (CharacterCodingException error) {
            return new Decision("MALFORMED", null, false);
        }
        List<Template> matches = templates.stream()
            .filter(item -> Arrays.equals(raw, item.canonicalBytes))
            .toList();
        if (matches.size() == 1) {
            return new Decision("EXACT_BYTES_MATCH", matches.get(0).id, true);
        }
        String normalized = normalize(decoded);
        matches = templates.stream()
            .filter(item -> normalized.equals(item.normalizedCanonical))
            .toList();
        if (matches.size() == 1) {
            return new Decision("EXACT_NORMALIZED_MATCH", matches.get(0).id, true);
        }
        String lexical = lexical(decoded);
        matches = templates.stream().filter(item -> templateMatches(item, lexical)).toList();
        if (matches.size() == 1) {
            return new Decision("SPDX_TEMPLATE_MATCH", matches.get(0).id, true);
        }
        if (matches.size() > 1) {
            return new Decision("MULTIPLE_TEMPLATE_MATCH", null, false);
        }
        return new Decision("NO_MATCH", null, false);
    }

    private static boolean templateMatches(Template template, String lexical) {
        if (template.id.equals("Apache-2.0")) {
            for (String base : template.apacheBases) {
                if (lexical.equals(base)) return true;
                String placeholder = "yyyy name of copyright owner";
                int position = base.indexOf(placeholder);
                if (position >= 0) {
                    String prefix = base.substring(0, position);
                    String suffix = base.substring(position + placeholder.length());
                    if (lexical.startsWith(prefix) && lexical.endsWith(suffix)) {
                        int end = lexical.length() - suffix.length();
                        int words = lexical.substring(prefix.length(), end).trim().split("\\s+").length;
                        if (words >= 1 && words <= 64) return true;
                    }
                }
            }
            return false;
        }
        return template.interpretedPattern.matcher(lexical).matches();
    }

    private static DocumentBuilderFactory secureFactory() throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
        factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        return factory;
    }

    private static Element firstTemplateElement(Document document) {
        for (String name : List.of("license", "exception")) {
            NodeList values = document.getElementsByTagNameNS("http://www.spdx.org/license", name);
            if (values.getLength() == 1) return (Element) values.item(0);
        }
        throw new IllegalArgumentException("SPDX XML contains no unique template element");
    }

    private static Element firstChild(Element parent, String localName) {
        NodeList values = parent.getElementsByTagNameNS("http://www.spdx.org/license", localName);
        if (values.getLength() != 1) throw new IllegalArgumentException("SPDX XML text ambiguity");
        return (Element) values.item(0);
    }

    private static String renderChildren(Node parent) {
        StringBuilder result = new StringBuilder();
        NodeList children = parent.getChildNodes();
        for (int index = 0; index < children.getLength(); index++) {
            Node child = children.item(index);
            if (child.getNodeType() == Node.TEXT_NODE) {
                result.append(literal(child.getNodeValue()));
            } else if (child.getNodeType() == Node.ELEMENT_NODE) {
                Element element = (Element) child;
                String tag = element.getLocalName();
                String rendered = renderChildren(element);
                switch (tag) {
                    case "optional" -> result.append("(?:").append(rendered).append(")?");
                    case "alt" -> result.append("(?:\\S+(?:\\s+\\S+){0,64})");
                    case "copyrightText" -> result.append("(?:\\S+(?:\\s+\\S+){0,64}\\s+)?");
                    case "bullet" -> result.append("(?:[a-z0-9]{1,4}\\s+)?");
                    case "br" -> result.append("\\s+");
                    default -> result.append(rendered);
                }
            }
        }
        return result.toString();
    }

    private static String literal(String value) {
        String lexical = lexical(value);
        if (lexical.isEmpty()) return "\\s*";
        return Arrays.stream(lexical.split("\\s+"))
            .map(Pattern::quote).reduce((a, b) -> a + "\\s+" + b).orElse("") + "\\s*";
    }

    private static String normalize(String value) {
        String nfc = Normalizer.normalize(value, Normalizer.Form.NFC)
            .replace("\r\n", "\n").replace('\r', '\n');
        String[] lines = nfc.split("\n", -1);
        StringBuilder result = new StringBuilder();
        for (int index = 0; index < lines.length; index++) {
            result.append(lines[index].replaceFirst("\\s+$", ""));
            if (index + 1 < lines.length) result.append('\n');
        }
        return result.toString().strip() + "\n";
    }

    private static String lexical(String value) {
        String normalized = Normalizer.normalize(value, Normalizer.Form.NFC)
            .toLowerCase(Locale.ROOT).replaceAll("https?://", "http://");
        return normalized.replaceAll("[^\\p{L}\\p{N}_]+", " ").trim().replaceAll("\\s+", " ");
    }

    private static List<String> apacheBases(String canonical) {
        List<String> values = new ArrayList<>();
        values.add(canonical);
        for (String heading : List.of(
            "terms and conditions for use reproduction and distribution ",
            "end of terms and conditions ")) {
            List<String> additions = values.stream()
                .map(value -> value.replaceFirst(Pattern.quote(heading), ""))
                .toList();
            values.addAll(additions);
        }
        String appendix = "appendix how to apply the apache license to your work ";
        List<String> additions = values.stream()
            .filter(value -> value.contains(appendix))
            .map(value -> value.substring(0, value.indexOf(appendix)).trim())
            .toList();
        values.addAll(additions);
        return values.stream().distinct().sorted().toList();
    }

    private static Path confined(Path root, String child) throws IOException {
        Path result = root.resolve(child).toRealPath();
        if (!result.startsWith(root)) throw new IllegalArgumentException("snapshot escape");
        return result;
    }

    private static String decodeStrict(byte[] value) throws CharacterCodingException {
        ByteBuffer buffer = ByteBuffer.wrap(value);
        String decoded = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).decode(buffer).toString();
        return decoded.startsWith("\ufeff") ? decoded.substring(1) : decoded;
    }

    private static String requireHash(String value) {
        if (!value.matches("[0-9a-f]{64}")) throw new IllegalArgumentException("invalid hash");
        return value;
    }

    private static String sha256(byte[] value) {
        try {
            return java.util.HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static String json(String value) {
        StringBuilder result = new StringBuilder("\"");
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            switch (character) {
                case '\\' -> result.append("\\\\");
                case '\"' -> result.append("\\\"");
                case '\n' -> result.append("\\n");
                case '\r' -> result.append("\\r");
                case '\t' -> result.append("\\t");
                default -> {
                    if (character < 0x20) result.append(String.format("\\u%04x", (int) character));
                    else result.append(character);
                }
            }
        }
        return result.append('\"').toString();
    }
}
