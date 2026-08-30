package dev.m341.synthetic;

public final class Adversarial01Overloads {
    public String foo(int value) { return "int"; }
    public String foo(String value) { return "string"; }
    public String foo(int left, int right) { return "pair"; }
}
