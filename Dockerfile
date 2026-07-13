FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# wine32 on Jammy requires i386 multiarch (bare wine32 package is obsolete).
RUN dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        wine64 \
        wine32:i386 \
        winetricks \
        qemu-user-static \
        file \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Default command is overridden by docker run
CMD ["file", "/workspace/README.md"]
