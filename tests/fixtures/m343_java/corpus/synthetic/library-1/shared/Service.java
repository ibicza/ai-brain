package dev.m343.liba.shared;
public interface Service {
    default boolean ready() { return true; }
    static int version() { return 1; }
}
