package dev.m343.libb.shared;
public record Service(String name, int version) {
    public Service { if (name == null) throw new IllegalArgumentException(); }
    public String label() { return name + version; }
}
