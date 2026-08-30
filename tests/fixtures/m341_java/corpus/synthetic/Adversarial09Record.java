package dev.m341.synthetic;

public record Adversarial09Record(String name, int count) {
    public Adversarial09Record { if (count < 0) throw new IllegalArgumentException(); }
    public String label() { return name + count; }
}
