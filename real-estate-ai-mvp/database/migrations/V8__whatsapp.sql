-- WhatsApp deliveries are notifications with channel WHATSAPP. The provider's message id is
-- indexed so delivery-status webhooks find their row without a workspace header.
CREATE INDEX idx_notification_deliveries_provider_message
  ON notification_deliveries ((data->>'providerMessageId'))
  WHERE data->>'providerMessageId' IS NOT NULL;
CREATE INDEX idx_notifications_provider_message
  ON notifications ((data->>'providerMessageId'))
  WHERE data->>'providerMessageId' IS NOT NULL;
