FROM google/cloud-sdk:slim

# System dependencies for Flutter + Android SDK
RUN apt-get update && apt-get install -y --no-install-recommends \
    git unzip xz-utils curl \
    openjdk-17-jdk-headless \
    libglu1-mesa \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Android SDK
ENV ANDROID_HOME=/opt/android-sdk
ENV PATH="${ANDROID_HOME}/cmdline-tools/latest/bin:${ANDROID_HOME}/platform-tools:${PATH}"

RUN mkdir -p "${ANDROID_HOME}/cmdline-tools" \
    && cd /tmp \
    && curl -fsSLO https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip \
    && unzip -q commandlinetools-linux-*.zip \
    && mv cmdline-tools "${ANDROID_HOME}/cmdline-tools/latest" \
    && rm commandlinetools-linux-*.zip

RUN yes | sdkmanager --licenses > /dev/null 2>&1 \
    && sdkmanager --install \
        "platform-tools" \
        "build-tools;35.0.0" \
        "platforms;android-35"

# Flutter SDK (pinned version)
ENV FLUTTER_HOME=/opt/flutter
ENV PATH="${FLUTTER_HOME}/bin:${PATH}"

RUN git clone --depth 1 --branch 3.41.2 \
        https://github.com/flutter/flutter.git "${FLUTTER_HOME}" \
    && flutter precache --android --web \
    && flutter config --no-analytics \
    && dart --disable-analytics

# Pre-create cache directories (overridden at runtime via env vars)
RUN mkdir -p /cache/pub /cache/gradle

COPY build.sh /build.sh
RUN chmod +x /build.sh

ENTRYPOINT ["/build.sh"]
