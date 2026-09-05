"""Metadata-only M-33.6e candidate pool and untouched-cache controls."""

from __future__ import annotations

import os
import urllib.parse
from collections import Counter
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    DEFAULT_REGISTRY_ROOT,
    load_disclosed_java_registry,
    verify_disclosed_java_registry,
)
from ai_brain.stage3.acquisition.m336d_final_pipeline import (
    CandidateSeed,
    _probe_one,
    frozen_candidate_seeds,
    frozen_prior_identity_denylist,
)

M336E_METADATA_POLICY_VERSION = "m336e.metadata-pool.v2"
M336E_MINIMUM_CANDIDATE_FAMILIES = 48
M336E_MINIMUM_ORGANIZATIONS = 40
M336E_MAXIMUM_CANDIDATES_PER_ORGANIZATION = 2
M336E_MAXIMUM_SOURCE_JAR_CONTENT_LENGTH = 4_000_000

# This is metadata only.  It freezes Maven coordinates and immutable SCM refs;
# it contains no source-JAR bytes, archive listings, source text or source facts.
_SEED_ROWS = (
    (
        "commons-codec",
        "apache-commons",
        "commons-codec",
        "commons-codec",
        "1.17.2",
        "https://github.com/apache/commons-codec.git",
        "refs/tags/rel/commons-codec-1.17.2",
    ),
    (
        "commons-text",
        "apache-commons",
        "org.apache.commons",
        "commons-text",
        "1.13.0",
        "https://github.com/apache/commons-text.git",
        "refs/tags/rel/commons-text-1.13.0",
    ),
    (
        "netty-buffer",
        "netty",
        "io.netty",
        "netty-buffer",
        "4.1.118.Final",
        "https://github.com/netty/netty.git",
        "refs/tags/netty-4.1.118.Final",
        ("buffer/src/main/java",),
    ),
    (
        "snappy-java",
        "xerial",
        "org.xerial.snappy",
        "snappy-java",
        "1.1.10.7",
        "https://github.com/xerial/snappy-java.git",
        "refs/tags/1.1.10.7",
    ),
    (
        "kryo",
        "esotericsoftware",
        "com.esotericsoftware",
        "kryo",
        "5.6.2",
        "https://github.com/EsotericSoftware/kryo.git",
        "refs/tags/kryo-parent-5.6.2",
    ),
    (
        "javassist",
        "jboss",
        "org.javassist",
        "javassist",
        "3.30.2-GA",
        "https://github.com/jboss-javassist/javassist.git",
        "refs/tags/rel_3_30_2_ga",
    ),
    (
        "asm",
        "ow2",
        "org.ow2.asm",
        "asm",
        "9.7.1",
        "https://gitlab.ow2.org/asm/asm.git",
        "refs/tags/ASM_9_7_1",
    ),
    (
        "bcprov",
        "bouncycastle",
        "org.bouncycastle",
        "bcprov-jdk18on",
        "1.80",
        "https://github.com/bcgit/bc-java.git",
        "refs/tags/r1rv80",
        ("core/src/main/java",),
    ),
    (
        "jsoup",
        "jhy",
        "org.jsoup",
        "jsoup",
        "1.18.3",
        "https://github.com/jhy/jsoup.git",
        "refs/tags/jsoup-1.18.3",
    ),
    (
        "retrofit",
        "square-retrofit",
        "com.squareup.retrofit2",
        "retrofit",
        "2.11.0",
        "https://github.com/square/retrofit.git",
        "refs/tags/2.11.0",
        ("retrofit/src/main/java",),
    ),
    (
        "rxjava3",
        "reactivex",
        "io.reactivex.rxjava3",
        "rxjava",
        "3.1.10",
        "https://github.com/ReactiveX/RxJava.git",
        "refs/tags/v3.1.10",
    ),
    (
        "metrics-core",
        "dropwizard",
        "io.dropwizard.metrics",
        "metrics-core",
        "4.2.30",
        "https://github.com/dropwizard/metrics.git",
        "refs/tags/v4.2.30",
        ("metrics-core/src/main/java",),
    ),
    (
        "quartz",
        "quartz-scheduler",
        "org.quartz-scheduler",
        "quartz",
        "2.3.2",
        "https://github.com/quartz-scheduler/quartz.git",
        "refs/tags/quartz-2.3.2",
        ("quartz-core/src/main/java",),
    ),
    (
        "xz",
        "tukaani",
        "org.tukaani",
        "xz",
        "1.10",
        "https://github.com/tukaani-project/xz-java.git",
        "refs/tags/v1.10",
    ),
    (
        "java-diff-utils",
        "java-diff-utils",
        "io.github.java-diff-utils",
        "java-diff-utils",
        "4.15",
        "https://github.com/java-diff-utils/java-diff-utils.git",
        "refs/tags/java-diff-utils-parent-4.15",
        ("java-diff-utils/src/main/java",),
    ),
    (
        "jool",
        "jooq",
        "org.jooq",
        "jool",
        "0.9.15",
        "https://github.com/jOOQ/jOOL.git",
        "refs/tags/version-0.9.15",
    ),
    (
        "reflections",
        "ronmamo",
        "org.reflections",
        "reflections",
        "0.10.2",
        "https://github.com/ronmamo/reflections.git",
        "refs/tags/0.10.2",
    ),
    (
        "minimal-json",
        "eclipsesource",
        "com.eclipsesource.minimal-json",
        "minimal-json",
        "0.9.5",
        "https://github.com/ralfstx/minimal-json.git",
        "refs/tags/0.9.5",
    ),
    (
        "jsoniter",
        "json-iterator",
        "com.jsoniter",
        "jsoniter",
        "0.9.23",
        "https://github.com/json-iterator/java.git",
        "refs/tags/0.9.23",
    ),
    (
        "dsl-json",
        "dslplatform",
        "com.dslplatform",
        "dsl-json-java8",
        "1.10.0",
        "https://github.com/ngs-doo/dsl-json.git",
        "refs/tags/v1.10.0",
        ("library/src/main/java",),
    ),
    (
        "xchart",
        "knowm",
        "org.knowm.xchart",
        "xchart",
        "3.8.8",
        "https://github.com/knowm/XChart.git",
        "refs/tags/xchart-3.8.8",
        ("xchart/src/main/java",),
    ),
    (
        "jfreechart",
        "jfree",
        "org.jfree",
        "jfreechart",
        "1.5.5",
        "https://github.com/jfree/jfreechart.git",
        "refs/tags/v1.5.5",
    ),
    (
        "miglayout-core",
        "miglayout",
        "com.miglayout",
        "miglayout-core",
        "11.4.2",
        "https://github.com/mikaelgrev/miglayout.git",
        "refs/tags/v11.4.2",
        ("core/src/main/java",),
    ),
    (
        "jansi",
        "fusesource",
        "org.fusesource.jansi",
        "jansi",
        "2.4.1",
        "https://github.com/fusesource/jansi.git",
        "refs/tags/jansi-2.4.1",
    ),
    (
        "jline-reader",
        "jline",
        "org.jline",
        "jline-reader",
        "3.29.0",
        "https://github.com/jline/jline3.git",
        "refs/tags/jline-parent-3.29.0",
        ("reader/src/main/java",),
    ),
    (
        "opencsv",
        "opencsv",
        "com.opencsv",
        "opencsv",
        "5.10",
        "https://github.com/cygri/opencsv.git",
        "refs/tags/opencsv-5.10",
    ),
    (
        "simpleflatmapper-csv",
        "simpleflatmapper",
        "org.simpleflatmapper",
        "sfm-csv",
        "8.2.3",
        "https://github.com/arnaudroger/SimpleFlatMapper.git",
        "refs/tags/v8.2.3",
        ("sfm-csv/src/main/java",),
    ),
    (
        "univocity-parsers",
        "univocity",
        "com.univocity",
        "univocity-parsers",
        "2.9.1",
        "https://github.com/uniVocity/univocity-parsers.git",
        "refs/tags/v2.9.1",
    ),
    (
        "rtree",
        "davidmoten",
        "com.github.davidmoten",
        "rtree",
        "0.12.0",
        "https://github.com/davidmoten/rtree.git",
        "refs/tags/0.12.0",
    ),
    (
        "h2",
        "h2database",
        "com.h2database",
        "h2",
        "2.3.232",
        "https://github.com/h2database/h2database.git",
        "refs/tags/version-2.3.232",
        ("h2/src/main",),
    ),
    (
        "postgresql-jdbc",
        "pgjdbc",
        "org.postgresql",
        "postgresql",
        "42.7.5",
        "https://github.com/pgjdbc/pgjdbc.git",
        "refs/tags/REL42.7.5",
        ("pgjdbc/src/main/java",),
    ),
    (
        "mysql-connector-j",
        "mysql",
        "com.mysql",
        "mysql-connector-j",
        "9.2.0",
        "https://github.com/mysql/mysql-connector-j.git",
        "refs/tags/9.2.0",
    ),
    (
        "mariadb-java-client",
        "mariadb",
        "org.mariadb.jdbc",
        "mariadb-java-client",
        "3.5.2",
        "https://github.com/mariadb-corporation/mariadb-connector-j.git",
        "refs/tags/3.5.2",
        ("src/main/java",),
    ),
    (
        "lettuce-core",
        "redis",
        "io.lettuce",
        "lettuce-core",
        "6.5.3.RELEASE",
        "https://github.com/redis/lettuce.git",
        "refs/tags/6.5.3.RELEASE",
    ),
    (
        "jedis",
        "redis",
        "redis.clients",
        "jedis",
        "5.2.0",
        "https://github.com/redis/jedis.git",
        "refs/tags/v5.2.0",
    ),
    (
        "mongodb-driver-core",
        "mongodb",
        "org.mongodb",
        "mongodb-driver-core",
        "5.3.1",
        "https://github.com/mongodb/mongo-java-driver.git",
        "refs/tags/r5.3.1",
        ("driver-core/src/main",),
    ),
    (
        "aws-sdk-core",
        "amazon",
        "software.amazon.awssdk",
        "sdk-core",
        "2.30.30",
        "https://github.com/aws/aws-sdk-java-v2.git",
        "refs/tags/2.30.30",
        ("core/sdk-core/src/main/java",),
    ),
    (
        "azure-core",
        "microsoft",
        "com.azure",
        "azure-core",
        "1.55.2",
        "https://github.com/Azure/azure-sdk-for-java.git",
        "refs/tags/azure-core_1.55.2",
        ("sdk/core/azure-core/src/main/java",),
    ),
    (
        "google-cloud-core",
        "googleapis",
        "com.google.cloud",
        "google-cloud-core",
        "2.48.0",
        "https://github.com/googleapis/java-core.git",
        "refs/tags/v2.48.0",
        ("google-cloud-core/src/main/java",),
    ),
    (
        "armeria",
        "linecorp",
        "com.linecorp.armeria",
        "armeria",
        "1.32.3",
        "https://github.com/line/armeria.git",
        "refs/tags/armeria-1.32.3",
        ("core/src/main/java",),
    ),
    (
        "undertow-core",
        "undertow",
        "io.undertow",
        "undertow-core",
        "2.3.18.Final",
        "https://github.com/undertow-io/undertow.git",
        "refs/tags/2.3.18.Final",
        ("core/src/main/java",),
    ),
    (
        "jetty-server",
        "jetty",
        "org.eclipse.jetty",
        "jetty-server",
        "12.0.16",
        "https://github.com/jetty/jetty.project.git",
        "refs/tags/jetty-12.0.16",
        ("jetty-core/jetty-server/src/main/java",),
    ),
    (
        "grizzly-http-server",
        "eclipse-ee4j",
        "org.glassfish.grizzly",
        "grizzly-http-server",
        "4.0.2",
        "https://github.com/eclipse-ee4j/grizzly.git",
        "refs/tags/4.0.2",
        ("modules/http-server/src/main/java",),
    ),
    (
        "vertx-core",
        "eclipse-vertx",
        "io.vertx",
        "vertx-core",
        "4.5.13",
        "https://github.com/eclipse-vertx/vert.x.git",
        "refs/tags/4.5.13",
        ("vertx-core/src/main/java",),
    ),
    (
        "nanohttpd",
        "nanohttpd",
        "org.nanohttpd",
        "nanohttpd",
        "2.3.1",
        "https://github.com/NanoHttpd/nanohttpd.git",
        "refs/tags/nanohttpd-project-2.3.1",
        ("core/src/main/java",),
    ),
    (
        "spark-core",
        "perwendel",
        "com.sparkjava",
        "spark-core",
        "2.9.4",
        "https://github.com/perwendel/spark.git",
        "refs/tags/2.9.4",
        ("spark-core/src/main/java",),
    ),
    (
        "zt-exec",
        "zeroturnaround",
        "org.zeroturnaround",
        "zt-exec",
        "1.12",
        "https://github.com/zeroturnaround/zt-exec.git",
        "refs/tags/1.12",
    ),
    (
        "mwiede-jsch",
        "mwiede",
        "com.github.mwiede",
        "jsch",
        "0.2.21",
        "https://github.com/mwiede/jsch.git",
        "refs/tags/0.2.21",
    ),
    (
        "oshi-core",
        "oshi",
        "com.github.oshi",
        "oshi-core",
        "6.6.5",
        "https://github.com/oshi/oshi.git",
        "refs/tags/oshi-parent-6.6.5",
        ("oshi-core/src/main/java",),
    ),
    (
        "mapdb",
        "jankotek",
        "org.mapdb",
        "mapdb",
        "3.1.0",
        "https://github.com/jankotek/mapdb.git",
        "refs/tags/mapdb-3.1.0",
    ),
    (
        "nitrite",
        "dizitart",
        "org.dizitart",
        "nitrite",
        "4.3.1",
        "https://github.com/nitrite/nitrite-java.git",
        "refs/tags/nitrite-4.3.1",
        ("nitrite/src/main/java",),
    ),
    (
        "orientdb-core",
        "orientdb",
        "com.orientechnologies",
        "orientdb-core",
        "3.2.37",
        "https://github.com/orientechnologies/orientdb.git",
        "refs/tags/3.2.37",
        ("core/src/main/java",),
    ),
    (
        "jgraphx",
        "jgraph",
        "com.github.vlsi.mxgraph",
        "jgraphx",
        "4.2.2",
        "https://github.com/jgraph/jgraphx.git",
        "refs/tags/v4.2.2",
    ),
    (
        "jgrapht-core",
        "jgrapht",
        "org.jgrapht",
        "jgrapht-core",
        "1.5.2",
        "https://github.com/jgrapht/jgrapht.git",
        "refs/tags/jgrapht-1.5.2",
        ("jgrapht-core/src/main/java",),
    ),
    (
        "graphstream-core",
        "graphstream",
        "org.graphstream",
        "gs-core",
        "2.0",
        "https://github.com/graphstream/gs-core.git",
        "refs/tags/2.0",
    ),
    (
        "ojalgo",
        "optimatika",
        "org.ojalgo",
        "ojalgo",
        "55.2.0",
        "https://github.com/optimatika/ojAlgo.git",
        "refs/tags/v55.2.0",
    ),
    (
        "exp4j",
        "objecthunter",
        "net.objecthunter",
        "exp4j",
        "0.4.8",
        "https://github.com/fasseg/exp4j.git",
        "refs/tags/0.4.8",
    ),
    (
        "javaparser-core",
        "javaparser",
        "com.github.javaparser",
        "javaparser-core",
        "3.26.3",
        "https://github.com/javaparser/javaparser.git",
        "refs/tags/javaparser-parent-3.26.3",
        ("javaparser-core/src/main/java",),
    ),
    (
        "antlr4-runtime",
        "antlr",
        "org.antlr",
        "antlr4-runtime",
        "4.13.2",
        "https://github.com/antlr/antlr4.git",
        "refs/tags/4.13.2",
        ("runtime/Java/src",),
    ),
    (
        "beanshell",
        "beanshell",
        "org.beanshell",
        "bsh",
        "2.1.1",
        "https://github.com/beanshell/beanshell.git",
        "refs/tags/2.1.1",
    ),
    (
        "janino",
        "janino",
        "org.codehaus.janino",
        "janino",
        "3.1.12",
        "https://github.com/janino-compiler/janino.git",
        "refs/tags/janino-parent-3.1.12",
        ("janino/src/main/java",),
    ),
    (
        "rhino",
        "mozilla",
        "org.mozilla",
        "rhino",
        "1.7.15",
        "https://github.com/mozilla/rhino.git",
        "refs/tags/Rhino1_7_15_Release",
        ("rhino/src/main/java",),
    ),
    (
        "mustache-compiler",
        "spullara",
        "com.github.spullara.mustache.java",
        "compiler",
        "0.9.14",
        "https://github.com/spullara/mustache.java.git",
        "refs/tags/mustache.java-0.9.14",
        ("compiler/src/main/java",),
    ),
    (
        "handlebars",
        "jknack",
        "com.github.jknack",
        "handlebars",
        "4.4.0",
        "https://github.com/jknack/handlebars.java.git",
        "refs/tags/v4.4.0",
        ("handlebars/src/main/java",),
    ),
    (
        "thymeleaf",
        "thymeleaf",
        "org.thymeleaf",
        "thymeleaf",
        "3.1.3.RELEASE",
        "https://github.com/thymeleaf/thymeleaf.git",
        "refs/tags/thymeleaf-3.1.3.RELEASE",
    ),
    (
        "commonmark",
        "commonmark",
        "org.commonmark",
        "commonmark",
        "0.24.0",
        "https://github.com/commonmark/commonmark-java.git",
        "refs/tags/commonmark-parent-0.24.0",
        ("commonmark/src/main/java",),
    ),
    (
        "flexmark",
        "vsch",
        "com.vladsch.flexmark",
        "flexmark",
        "0.64.8",
        "https://github.com/vsch/flexmark-java.git",
        "refs/tags/0.64.8",
        ("flexmark/src/main/java",),
    ),
    (
        "woodstox-core",
        "fasterxml",
        "com.fasterxml.woodstox",
        "woodstox-core",
        "7.1.0",
        "https://github.com/FasterXML/woodstox.git",
        "refs/tags/woodstox-core-7.1.0",
        ("src/main/java",),
    ),
    (
        "stax2-api",
        "fasterxml",
        "org.codehaus.woodstox",
        "stax2-api",
        "4.2.2",
        "https://github.com/FasterXML/stax2-api.git",
        "refs/tags/stax2-api-4.2.2",
    ),
    (
        "xstream",
        "xstream",
        "com.thoughtworks.xstream",
        "xstream",
        "1.4.21",
        "https://github.com/x-stream/xstream.git",
        "refs/tags/XSTREAM_1_4_21",
        ("xstream/src/java",),
    ),
    (
        "jimfs",
        "google-jimfs",
        "com.google.jimfs",
        "jimfs",
        "1.3.0",
        "https://github.com/google/jimfs.git",
        "refs/tags/v1.3.0",
        ("jimfs/src/main/java",),
    ),
    (
        "cglib",
        "cglib",
        "cglib",
        "cglib",
        "3.3.0",
        "https://github.com/cglib/cglib.git",
        "refs/tags/RELEASE_3_3_0",
        ("cglib/src/main/java",),
    ),
    (
        "ehcache",
        "ehcache",
        "org.ehcache",
        "ehcache",
        "3.10.8",
        "https://github.com/ehcache/ehcache3.git",
        "refs/tags/v3.10.8",
        ("ehcache/src/main/java",),
    ),
    (
        "cache2k-core",
        "cache2k",
        "org.cache2k",
        "cache2k-core",
        "2.6.1.Final",
        "https://github.com/cache2k/cache2k.git",
        "refs/tags/v2.6.1.Final",
        ("cache2k-core/src/main/java",),
    ),
    (
        "resilience4j-core",
        "resilience4j",
        "io.github.resilience4j",
        "resilience4j-core",
        "2.3.0",
        "https://github.com/resilience4j/resilience4j.git",
        "refs/tags/v2.3.0",
        ("resilience4j-core/src/main/java",),
    ),
    (
        "jodd-core",
        "jodd",
        "org.jodd",
        "jodd-core",
        "6.3.0",
        "https://github.com/oblac/jodd.git",
        "refs/tags/v6.3.0",
        ("jodd-core/src/main/java",),
    ),
    (
        "tinylog-impl",
        "tinylog",
        "org.tinylog",
        "tinylog-impl",
        "2.7.0",
        "https://github.com/tinylog-org/tinylog.git",
        "refs/tags/v2.7.0",
        ("tinylog-impl/src/main/java",),
    ),
    (
        "logback-core",
        "qos-logback",
        "ch.qos.logback",
        "logback-core",
        "1.5.16",
        "https://github.com/qos-ch/logback.git",
        "refs/tags/v_1.5.16",
        ("logback-core/src/main/java",),
    ),
)


def _seed(row) -> CandidateSeed:
    required = row[:7]
    prefixes = row[7] if len(row) == 8 else ()
    return CandidateSeed(*required, repository_source_prefixes=tuple(prefixes))


_SEEDS = tuple(_seed(row) for row in _SEED_ROWS)


def build_m336e_disclosed_identity_denylist(
    registry_root: Path = DEFAULT_REGISTRY_ROOT,
) -> dict:
    """Bind every known prior identity class before any V4 metadata request."""

    verify_disclosed_java_registry(registry_root)
    entries = load_disclosed_java_registry(registry_root)
    historical = frozen_prior_identity_denylist()
    m336d = frozen_candidate_seeds()
    coordinates = {
        *historical["excluded_coordinates"],
        *(f"{item.group_id}:{item.artifact_id}:{item.version}" for item in m336d),
        *(item.coordinate for item in entries),
    }
    source_urls = {
        *historical["excluded_source_urls"],
        *(_source_url(item) for item in m336d),
        *(item.source_url for item in entries),
    }
    body = {
        "schema_version": 2,
        "registry_entry_count": len(entries),
        "registry_entry_hashes": tuple(sorted(item.entry_hash for item in entries)),
        "excluded_family_ids": tuple(
            sorted(
                {
                    *historical["excluded_family_ids"],
                    *(item.family_id for item in m336d),
                }
            )
        ),
        "excluded_coordinates": tuple(sorted(coordinates)),
        "excluded_source_urls": tuple(sorted(source_urls)),
        "excluded_scm_repositories": tuple(
            sorted(
                {
                    *historical["excluded_scm_repositories"],
                    *(item.scm_repository for item in m336d),
                }
            )
        ),
        "excluded_source_archive_hashes": tuple(
            sorted({item.archive_hash for item in entries})
        ),
        "excluded_source_tree_hashes": tuple(
            sorted({item.source_tree_hash for item in entries})
        ),
    }
    return {**body, "denylist_hash": content_hash(body)}


def fresh_metadata_candidate_seeds(
    registry_root: Path = DEFAULT_REGISTRY_ROOT,
) -> tuple[CandidateSeed, ...]:
    """Return the V4 metadata identities after strict disclosed-overlap checks."""

    denylist = build_m336e_disclosed_identity_denylist(registry_root)
    organizations = Counter(item.organization_id for item in _SEEDS)
    identities = {
        "family": tuple(item.family_id for item in _SEEDS),
        "coordinate": tuple(
            f"{item.group_id}:{item.artifact_id}:{item.version}" for item in _SEEDS
        ),
        "source_url": tuple(_source_url(item) for item in _SEEDS),
        "scm_repository": tuple(item.scm_repository for item in _SEEDS),
    }
    if (
        len(_SEEDS) < M336E_MINIMUM_CANDIDATE_FAMILIES
        or len(organizations) < M336E_MINIMUM_ORGANIZATIONS
        or max(organizations.values()) > M336E_MAXIMUM_CANDIDATES_PER_ORGANIZATION
    ):
        raise AssertionError("M-33.6e metadata seed diversity contract failed")
    if any(len(values) != len(set(values)) for values in identities.values()):
        raise AssertionError("M-33.6e metadata seeds contain duplicate identities")
    denylist_fields = {
        "family": "excluded_family_ids",
        "coordinate": "excluded_coordinates",
        "source_url": "excluded_source_urls",
        "scm_repository": "excluded_scm_repositories",
    }
    for identity_class, values in identities.items():
        denied = set(denylist[denylist_fields[identity_class]])
        if set(values) & denied:
            raise AssertionError(
                f"M-33.6e metadata seed overlaps disclosed {identity_class}"
            )
    if any(_metadata_risk_reason(item) for item in _SEEDS):
        raise AssertionError("M-33.6e metadata seed is an obvious non-runtime role")
    return _SEEDS


def scan_m336e_local_cache_names(
    roots: tuple[tuple[str, Path], ...],
    *,
    platform: str,
    seeds: tuple[CandidateSeed, ...] | None = None,
) -> dict:
    """Inspect only names/layout metadata; never open a candidate source body."""

    seeds = seeds if seeds is not None else fresh_metadata_candidate_seeds()
    source_names = {
        f"{item.artifact_id}-{item.version}-sources.jar".casefold(): item
        for item in seeds
    }
    repository_names = {
        item: item.scm_repository.removesuffix(".git").rsplit("/", 1)[-1].casefold()
        for item in seeds
    }
    rows_by_key = {}

    def record(seed: CandidateSeed, cache_class: str, reason: str) -> None:
        row_body = {
            "candidate_id": seed.family_id,
            "cache_class": cache_class,
            "matched_metadata_identity": _source_url(seed)
            if reason == "EXACT_SOURCE_JAR_FILENAME_PRESENT"
            else seed.scm_repository,
            "excluded": True,
            "reason": reason,
        }
        rows_by_key[(seed.family_id, cache_class, reason)] = {
            **row_body,
            "receipt_hash": content_hash(row_body),
        }

    for cache_class, root in roots:
        if not root.exists():
            continue
        for directory, children, files in os.walk(root):
            directory_name = Path(directory).name.casefold()
            child_names = {name.casefold() for name in children}
            file_names = {name.casefold() for name in files}
            has_source_layout = "src" in child_names or any(
                name.endswith(".java") for name in file_names
            )
            has_git_metadata = ".git" in child_names or ".git" in file_names
            for seed, repository_name in repository_names.items():
                names = {
                    seed.family_id.casefold(),
                    repository_name,
                    f"{repository_name}-{seed.version}".casefold(),
                    f"{seed.family_id}-{seed.version}".casefold(),
                }
                if directory_name in names and has_git_metadata:
                    record(seed, cache_class, "SCM_CHECKOUT_DIRECTORY_NAME_PRESENT")
                elif directory_name in names and has_source_layout:
                    record(seed, cache_class, "EXTRACTED_SOURCE_ROOT_NAME_PRESENT")
            for name in files:
                lowered = name.casefold()
                seed = source_names.get(lowered)
                if seed is not None:
                    record(seed, cache_class, "EXACT_SOURCE_JAR_FILENAME_PRESENT")
                    continue
                if not lowered.endswith((".zip", ".tar", ".tar.gz", ".tgz")):
                    continue
                for candidate, repository_name in repository_names.items():
                    version_tokens = {
                        candidate.version.casefold(),
                        candidate.scm_ref.rsplit("/", 1)[-1].casefold(),
                    }
                    if (
                        candidate.family_id.casefold() in lowered
                        or repository_name in lowered
                    ) and any(token in lowered for token in version_tokens):
                        record(candidate, cache_class, "SCM_ARCHIVE_FILENAME_PRESENT")
    ordered = tuple(rows_by_key[key] for key in sorted(rows_by_key))
    body = {
        "schema_version": 2,
        "platform": platform,
        "candidate_count": len(seeds),
        "inspected_root_classes": tuple(sorted({item[0] for item in roots})),
        "source_body_bytes_read": 0,
        "matches": ordered,
        "excluded_family_ids": tuple(
            sorted({item["candidate_id"] for item in ordered})
        ),
    }
    return {**body, "receipt_hash": content_hash(body)}


def probe_metadata_pool_v4(
    *,
    windows_cache: dict,
    karina_cache: dict,
    timestamp: str,
    host: str,
    probe_one=_probe_one,
    seeds: tuple[CandidateSeed, ...] | None = None,
) -> tuple[dict, dict, dict]:
    """Probe only the explicitly allowed metadata and construct pool V4."""

    for report in (windows_cache, karina_cache):
        if report.get("source_body_bytes_read") != 0:
            raise ValueError("untouched cache census reports source-body reads")
    allowed_seeds = seeds if seeds is not None else fresh_metadata_candidate_seeds()
    excluded = set(windows_cache["excluded_family_ids"]) | set(
        karina_cache["excluded_family_ids"]
    )
    candidates = []
    network_receipts = []
    failures = []
    for seed in allowed_seeds:
        if seed.family_id in excluded:
            continue
        try:
            row, receipts = probe_one(seed, timestamp=timestamp, host=host)
            _verify_metadata_only_receipts(seed, receipts)
        except Exception as exc:  # noqa: BLE001 - each failed identity is evidence
            failure_body = {
                "family_id": seed.family_id,
                "error_type": type(exc).__name__,
                "error": str(exc)[:240],
            }
            failures.append(
                {**failure_body, "failure_hash": content_hash(failure_body)}
            )
            continue
        network_receipts.extend(receipts)
        risk_reason = _metadata_row_risk_reason(row)
        if risk_reason is not None:
            failure_body = {
                "family_id": seed.family_id,
                "error_type": "METADATA_RISK_REJECTION",
                "error": risk_reason,
            }
            failures.append(
                {**failure_body, "failure_hash": content_hash(failure_body)}
            )
            continue
        candidates.append(row)
    candidates = tuple(sorted(candidates, key=lambda item: item["family_id"]))
    organizations = Counter(item["organization_id"] for item in candidates)
    if (
        len(candidates) < M336E_MINIMUM_CANDIDATE_FAMILIES
        or len(organizations) < M336E_MINIMUM_ORGANIZATIONS
        or max(organizations.values(), default=0)
        > M336E_MAXIMUM_CANDIDATES_PER_ORGANIZATION
    ):
        raise ValueError("actual metadata pool misses V4 size/diversity bounds")
    if any(item["requirement"] != "OPTIONAL" for item in candidates):
        raise ValueError("all V4 candidates must remain optional")
    body = {
        "schema_version": 2,
        "policy_version": M336E_METADATA_POLICY_VERSION,
        "candidate_count": len(candidates),
        "organization_count": len(organizations),
        "maximum_candidates_per_organization": max(organizations.values()),
        "required_candidate_count": 0,
        "optional_candidate_count": len(candidates),
        "pre_f20_source_body_bytes_received": 0,
        "claims_final_eligibility": False,
        "candidates": candidates,
        "failed_seed_receipt_hashes": tuple(
            sorted(item["failure_hash"] for item in failures)
        ),
    }
    pool = {**body, "pool_hash": content_hash(body)}
    receipt_body = {
        "schema_version": 2,
        "request_count": len(network_receipts),
        "source_jar_get_count": 0,
        "source_jar_head_count": sum(
            item["method"] == "HEAD" and item["requested_url"].endswith("-sources.jar")
            for item in network_receipts
        ),
        "source_body_bytes_received": 0,
        "forbidden_body_request_count": 0,
        "receipts": tuple(
            sorted(network_receipts, key=lambda item: item["receipt_hash"])
        ),
        "failures": tuple(sorted(failures, key=lambda item: item["family_id"])),
    }
    receipts = {**receipt_body, "report_hash": content_hash(receipt_body)}
    scenarios = build_metadata_failure_scenarios_v4(
        candidates, locally_excluded=tuple(sorted(excluded))
    )
    return pool, receipts, scenarios


def validate_metadata_pool_v4(
    pool: dict, registry_root: Path = DEFAULT_REGISTRY_ROOT
) -> tuple[dict, ...]:
    """Validate the F20 metadata pool and all disclosed-identity exclusions."""

    body = dict(pool)
    claimed = body.pop("pool_hash", None)
    if content_hash(body) != claimed or pool.get("schema_version") != 2:
        raise ValueError("V4 candidate pool hash/schema mismatch")
    candidates = tuple(pool["candidates"])
    organizations = Counter(item["organization_id"] for item in candidates)
    if (
        pool.get("policy_version") != M336E_METADATA_POLICY_VERSION
        or len(candidates) < M336E_MINIMUM_CANDIDATE_FAMILIES
        or len(organizations) < M336E_MINIMUM_ORGANIZATIONS
        or max(organizations.values(), default=0)
        > M336E_MAXIMUM_CANDIDATES_PER_ORGANIZATION
        or pool.get("required_candidate_count") != 0
        or pool.get("optional_candidate_count") != len(candidates)
        or pool.get("pre_f20_source_body_bytes_received") != 0
        or pool.get("claims_final_eligibility") is not False
        or any(item.get("requirement") != "OPTIONAL" for item in candidates)
        or any(_metadata_row_risk_reason(item) is not None for item in candidates)
    ):
        raise ValueError("V4 candidate pool policy mismatch")
    family_ids = tuple(item["family_id"] for item in candidates)
    if len(family_ids) != len(set(family_ids)):
        raise ValueError("V4 candidate pool contains duplicate families")
    seeds = {
        item.family_id: item for item in fresh_metadata_candidate_seeds(registry_root)
    }
    if set(family_ids) - set(seeds):
        raise ValueError("V4 candidate pool contains an identity outside frozen seeds")
    denylist = build_m336e_disclosed_identity_denylist(registry_root)
    for item in candidates:
        candidate_body = dict(item)
        policy_hash = candidate_body.pop("policy_hash", None)
        if content_hash(candidate_body) != policy_hash:
            raise ValueError("V4 candidate policy hash mismatch")
        if (
            item["coordinate"] in denylist["excluded_coordinates"]
            or item["source_url"] in denylist["excluded_source_urls"]
            or item["scm_repository"] in denylist["excluded_scm_repositories"]
        ):
            raise ValueError("V4 candidate pool overlaps disclosed identities")
    return candidates


def build_metadata_failure_scenarios_v4(candidates, *, locally_excluded=()):
    """Run real-ID correlated failures without positional list slicing."""

    candidates = tuple(candidates)
    families = tuple(item["family_id"] for item in candidates)
    organizations = tuple(sorted({item["organization_id"] for item in candidates}))
    scenarios = [(f"individual:{family}", {family}) for family in families] + [
        (
            f"organization:{organization}",
            {
                item["family_id"]
                for item in candidates
                if item["organization_id"] == organization
            },
        )
        for organization in organizations
    ]
    scenarios.extend(
        (
            f"deterministic-25-hash-partition-{partition}",
            {
                family
                for family in families
                if int(content_hash(("m336e-v4-25", family)), 16) % 4 == partition
            },
        )
        for partition in range(4)
    )
    scenarios.extend(
        (
            f"deterministic-50-hash-partition-{partition}",
            {
                family
                for family in families
                if int(content_hash(("m336e-v4-50", family)), 16) % 2 == partition
            },
        )
        for partition in range(2)
    )
    without_sidecars = {
        item["family_id"]
        for item in candidates
        if not item["source_sha256_sidecar_available"]
    }
    multi_license = {
        item["family_id"]
        for item in candidates
        if len(item["pom_license_declarations"]) != 1
        or item["pom_license_declarations"][0][0] == "NOASSERTION"
    }
    host_counts = Counter(
        urllib.parse.urlsplit(item["scm_repository"]).hostname for item in candidates
    )
    largest_host_count = max(host_counts.values(), default=0)
    largest_hosts = {
        name for name, count in host_counts.items() if count == largest_host_count
    }
    sizes = sorted(item["source_content_length"] for item in candidates)
    p75 = sizes[max(0, ((3 * len(sizes) + 3) // 4) - 1)]
    scenarios.extend(
        (
            ("without-checksum-sidecars", without_sidecars),
            ("scm-only-authenticity", without_sidecars),
            ("multi-license-review", multi_license),
            (
                "largest-host-concentration",
                {
                    item["family_id"]
                    for item in candidates
                    if urllib.parse.urlsplit(item["scm_repository"]).hostname
                    in largest_hosts
                },
            ),
            (
                "github-metadata-outage",
                {
                    item["family_id"]
                    for item in candidates
                    if urllib.parse.urlsplit(item["scm_repository"]).hostname
                    == "github.com"
                },
            ),
            (
                "maven-checksum-outage",
                {
                    item["family_id"]
                    for item in candidates
                    if item["source_sha256_sidecar_available"]
                },
            ),
            (
                "apache-hosted-correlation-failure",
                {
                    item["family_id"]
                    for item in candidates
                    if "/apache/" in item["scm_repository"].casefold()
                },
            ),
            (
                "size-tail-failure",
                {
                    item["family_id"]
                    for item in candidates
                    if item["source_content_length"] >= p75
                },
            ),
            ("local-cache-exclusions", set(locally_excluded)),
        )
    )
    rows = []
    for scenario_id, failed in scenarios:
        survivors = tuple(family for family in families if family not in failed)
        survivor_organizations = tuple(
            sorted(
                {
                    item["organization_id"]
                    for item in candidates
                    if item["family_id"] in survivors
                }
            )
        )
        row_body = {
            "scenario_id": scenario_id,
            "failed_family_ids": tuple(sorted(failed)),
            "surviving_optional_candidate_ids": survivors,
            "surviving_organization_ids": survivor_organizations,
            "advisory_potential_root_count": len(survivors),
            "claims_final_eligibility": False,
        }
        rows.append({**row_body, "scenario_hash": content_hash(row_body)})
    fifty = tuple(
        item for item in rows if item["scenario_id"].startswith("deterministic-50-")
    )
    minimum_50 = min(item["advisory_potential_root_count"] for item in fifty)
    body = {
        "schema_version": 2,
        "scenario_count": len(rows),
        "individual_candidate_scenario_count": len(families),
        "organization_scenario_count": len(organizations),
        "minimum_potential_roots_after_50_percent_loss": minimum_50,
        "preferred_five_potential_roots_survive": minimum_50 >= 5,
        "minimum_three_potential_roots_survive": minimum_50 >= 3,
        "claims_final_eligibility": False,
        "scenarios": tuple(rows),
    }
    return {**body, "report_hash": content_hash(body)}


def _verify_metadata_only_receipts(seed: CandidateSeed, receipts) -> None:
    source_url = _source_url(seed)
    if not receipts:
        raise ValueError("metadata probe emitted no request receipts")
    for receipt in receipts:
        url = receipt["requested_url"]
        method = receipt["method"]
        byte_count = receipt["bytes_received"]
        if url == source_url and (method != "HEAD" or byte_count != 0):
            raise ValueError("metadata probe attempted a source-JAR body request")
        if url.startswith(source_url) and url not in {
            source_url + ".sha256",
            source_url + ".asc",
            source_url,
        }:
            raise ValueError("metadata probe requested an unapproved source endpoint")
        if method not in {"GET", "HEAD", "GIT_LS_REMOTE"}:
            raise ValueError("metadata probe used an unapproved request method")


def _metadata_risk_reason(seed: CandidateSeed) -> str | None:
    identity = f"{seed.family_id} {seed.artifact_id}".casefold()
    risk_tokens = (
        "annotation",
        "-bom",
        "-parent",
        "maven-plugin",
        "gradle-plugin",
        "processor",
        "generator",
        "native",
        "test-fixture",
        "benchmark",
        "-shaded",
        "-all",
        "starter",
        "kotlin",
        "scala",
    )
    return next((token for token in risk_tokens if token in identity), None)


def _metadata_row_risk_reason(row: dict) -> str | None:
    if row.get("packaging") != "jar":
        return "PACKAGING_IS_NOT_JAR"
    length = row.get("source_content_length")
    if not isinstance(length, int) or isinstance(length, bool) or length <= 0:
        return "SOURCE_JAR_LENGTH_IS_NOT_POSITIVE"
    if length > M336E_MAXIMUM_SOURCE_JAR_CONTENT_LENGTH:
        return "SOURCE_JAR_LENGTH_ABOVE_FROZEN_BOUND"
    return None


def _source_url(seed: CandidateSeed) -> str:
    base = "https://repo.maven.apache.org/maven2"
    group = seed.group_id.replace(".", "/")
    name = f"{seed.artifact_id}-{seed.version}-sources.jar"
    return f"{base}/{group}/{seed.artifact_id}/{seed.version}/{name}"
