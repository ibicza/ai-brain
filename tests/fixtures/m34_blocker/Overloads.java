package dev.m34;

public class Overloads {
    public String foo(int value) { return "int"; }
    public String foo(String value) { return "string"; }
    public String foo(int left, int right) { return "pair"; }
}
