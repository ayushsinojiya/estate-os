package com.estraos.integration;

import java.util.Arrays;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class IntegrationConfiguration {
    private final Environment environment;
    private final boolean mock;

    public IntegrationConfiguration(Environment environment) {
        this.environment = environment;
        String mode = environment.getProperty("app.integrations.mode", "rest");
        if (!"mock".equals(mode) && !"rest".equals(mode)) throw new IllegalStateException("app.integrations.mode must be rest or mock");
        this.mock = "mock".equals(mode);
        if (mock && Arrays.stream(environment.getActiveProfiles()).noneMatch(profile -> profile.equals("demo") || profile.equals("test")))
            throw new IllegalStateException("Mock integrations require an explicit demo or test Spring profile");
        if (mock && Arrays.stream(environment.getActiveProfiles()).anyMatch(profile -> profile.equals("prod") || profile.equals("production")))
            throw new IllegalStateException("Mock integrations cannot run with a production Spring profile");
    }

    /** The knowledge service is used for real whenever its URL is configured, even in mock mode. */
    @Bean public RagServiceClient ragServiceClient() {
        boolean configured = !environment.getProperty("app.integrations.rag.url", "").isBlank();
        return mock && !configured ? new MockRagServiceClient() : new RestRagServiceClient(http("rag"));
    }
    @Bean public VoiceAgentServiceClient voiceAgentServiceClient() {
        return mock ? new MockVoiceAgentServiceClient() : new RestVoiceAgentServiceClient(http("voice"));
    }
    @Bean public NotificationServiceClient notificationServiceClient() {
        return mock ? new MockNotificationServiceClient() : new RestNotificationServiceClient(http("notification"));
    }
    /**
     * Mock in mock mode. In REST mode the Cloud API client when its credentials are set, otherwise
     * a client that records every send as failed: WhatsApp is optional, unlike the other services.
     */
    @Bean public WhatsAppClient whatsAppClient() {
        if (mock) return new MockWhatsAppClient();
        String phoneNumberId = environment.getProperty("app.whatsapp.phone-number-id", "");
        String token = environment.getProperty("app.whatsapp.access-token", "");
        if (phoneNumberId.isBlank() || token.isBlank()) return new DisabledWhatsAppClient();
        String version = environment.getProperty("app.whatsapp.api-version", "v21.0");
        if (!version.matches("v[0-9]{1,3}\\.[0-9]{1,3}")) throw new IllegalStateException("WHATSAPP_API_VERSION must look like v21.0");
        return new RestWhatsAppClient(new ProviderHttpClient("whatsapp", "https://graph.facebook.com/" + version, token,
            environment.getProperty("app.integrations.connect-timeout-ms", Integer.class, 3000),
            environment.getProperty("app.integrations.read-timeout-ms", Integer.class, 10000)), phoneNumberId);
    }

    private ProviderHttpClient http(String service) {
        return new ProviderHttpClient(service, environment.getProperty("app.integrations." + service + ".url", ""),
            environment.getProperty("app.integrations." + service + ".api-key", ""),
            environment.getProperty("app.integrations.connect-timeout-ms", Integer.class, 3000),
            environment.getProperty("app.integrations.read-timeout-ms", Integer.class, 10000));
    }
}
