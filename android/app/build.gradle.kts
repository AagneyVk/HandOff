plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "dev.handoff.client"
    compileSdk = 35

    defaultConfig {
        applicationId = "dev.handoff.client"
        minSdk = 26
        targetSdk = 35
        versionCode = 2
        versionName = "1.0.0-dev"
    }

    buildFeatures { compose = true }
}

dependencies {
    implementation("androidx.activity:activity-compose:1.10.0")
    implementation("androidx.compose.ui:ui:1.7.6")
    implementation("androidx.compose.ui:ui-tooling-preview:1.7.6")
    implementation("androidx.compose.material3:material3:1.3.1")
    debugImplementation("androidx.compose.ui:ui-tooling:1.7.6")
}
