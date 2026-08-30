package dev.m341.synthetic;

import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

public final class Adversarial12TypeAnnotations {
    @Target(ElementType.TYPE_USE) public @interface Mark { }
    public @Mark String marked(@Mark String value) { return value; }
}
