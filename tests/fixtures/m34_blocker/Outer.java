package dev.m34;

public class Outer {
    public static class Inner {
        public String same(int value) { return "inner"; }
    }

    public static class OtherInner {
        public String same(int value) { return "other"; }
    }
}
