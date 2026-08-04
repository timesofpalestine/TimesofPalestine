plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "ps.timesofpalestine.sanad"
    compileSdk = 34

    defaultConfig {
        applicationId = "ps.timesofpalestine.sanad"
        minSdk = 24
        targetSdk = 34
        versionCode = 3
        versionName = "0.3.0-alpha"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("com.google.android.material:material:1.12.0")
}
