package dev.m341.synthetic;

public final class Adversarial20LocalType {
    public String outer(String value) {
        class Local { String same(String input) { return input; } }
        return new Local().same(value);
    }
}
