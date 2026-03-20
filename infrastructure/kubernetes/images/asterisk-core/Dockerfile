# =============================================================================
# Asterisk Core — Build Asterisk 20.18.2 from source (amd64)
# =============================================================================
# Tagged as build cache. Used as base image by asterisk-headless.

FROM debian:bookworm AS asterisk-builder

ENV DEBIAN_FRONTEND=noninteractive
ENV ASTERISK_VERSION=20.18.2

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ make patch wget ca-certificates \
    libedit-dev libssl-dev libxml2-dev libsqlite3-dev uuid-dev \
    libsrtp2-dev libspandsp-dev libcurl4-openssl-dev libjansson-dev \
    libbluetooth-dev unixodbc-dev libncurses-dev libnewt-dev \
    libcap-dev libneon27-dev libgmime-3.0-dev liblua5.2-dev \
    libiksemel-dev libresample1-dev libspeex-dev libspeexdsp-dev \
    libtiff-dev libfftw3-dev freetds-dev libpq-dev libcorosync-common-dev \
    libcpg-dev libcfg-dev libsnmp-dev libical-dev \
    autoconf automake libtool pkg-config bison flex \
    python3 python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src

RUN wget -q "https://downloads.asterisk.org/pub/telephony/asterisk/asterisk-${ASTERISK_VERSION}.tar.gz" \
    && tar xzf "asterisk-${ASTERISK_VERSION}.tar.gz" \
    && rm "asterisk-${ASTERISK_VERSION}.tar.gz"

WORKDIR /usr/src/asterisk-${ASTERISK_VERSION}

RUN ./configure \
    --with-pjproject-bundled \
    --with-jansson-bundled \
    --with-crypto \
    --with-ssl \
    --with-srtp \
    --with-spandsp

RUN make menuselect/cmenuselect menuselect/nmenuselect menuselect/gmenuselect menuselect/menuselect menuselect-tree

# Disable modules we don't need
RUN menuselect/menuselect --disable chan_dahdi --disable chan_motif \
    --disable chan_console --disable chan_alsa --disable chan_mgcp \
    --disable chan_sip --disable chan_skinny menuselect.makeopts
# Disable codecs without deps
RUN menuselect/menuselect --disable codec_opus --disable codec_silk \
    --disable codec_g729a menuselect.makeopts
# Disable apps without deps
RUN menuselect/menuselect --disable app_meetme --disable app_osplookup \
    menuselect.makeopts
# Enable critical build deps
RUN menuselect/menuselect --enable res_fax --enable res_pjsip \
    --enable res_crypto --enable DONT_OPTIMIZE --enable G711_NEW_ALGORITHM \
    --enable BUILD_NATIVE --enable OPTIONAL_API menuselect.makeopts
# Enable sounds
RUN menuselect/menuselect --enable CORE-SOUNDS-EN-WAV --enable CORE-SOUNDS-EN-ULAW \
    --enable CORE-SOUNDS-EN-GSM --enable CORE-SOUNDS-EN-G722 \
    --enable MOH-OPSOUND-WAV \
    --enable EXTRA-SOUNDS-EN-WAV --enable EXTRA-SOUNDS-EN-ULAW \
    --enable EXTRA-SOUNDS-EN-GSM --enable EXTRA-SOUNDS-EN-G722 \
    menuselect.makeopts

RUN make -j$(nproc)
RUN make install
RUN make config
RUN make install-headers
RUN ldconfig
