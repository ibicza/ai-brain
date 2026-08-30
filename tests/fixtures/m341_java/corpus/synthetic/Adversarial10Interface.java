package dev.m341.synthetic;

public interface Adversarial10Interface {
    default int increment(int value) { return value + 1; }
    static int identity(int value) { return value; }
}
