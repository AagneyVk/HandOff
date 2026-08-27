plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "dev.handoff.client"
    compileSdk = 35

    defaultConfig {
        applicationId = "dev.handoff.client"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.0.1"
    }

    buildFeatures { compose = true }
    composeOptions { kotlinCompilerExtensionVersion = "1.5.15" }
}

dependencies {
    implementation("androidx.activity:activity-compose:1.10.0")
    implementation("androidx.compose.ui:ui:1.7.6")
    implementation("androidx.compose.ui:ui-tooling-preview:1.7.6")
    implementation("androidx.compose.material3:material3:1.3.1")
    debugImplementation("androidx.compose.ui:ui-tooling:1.7.6")
}
