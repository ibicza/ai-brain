package dev.m341.synthetic;

public final class Adversarial14TextBlocks {
    private static final String TEXT = """
        not // a comment { }
        not /* a block */ either
        """;
    public String text() { return "url://host/{value}" + TEXT; }
}
