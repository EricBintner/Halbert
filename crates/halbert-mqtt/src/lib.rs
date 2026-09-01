//! # halbert-mqtt
//!
//! MQTT client and device state cache for the Halbert native device bus.
//!
//! This crate wraps the MQTT 3.1.1/5.0 protocol (via `rumqttc`) to provide:
//! - Connection management with auto-reconnect
//! - QoS-aware publish/subscribe
//! - In-memory device state cache (retained messages + last-will)
//!
//! ## Stability
//!
//! The MQTT transport layer is a frozen OASIS standard. The trait contracts
//! defined here (`MqttClient`, `DeviceStateCache`) are stable and will not
//! change. Application logic (device registry, entity mapping) stays in Python.

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use thiserror::Error;

/// Errors returned by MQTT operations.
#[derive(Debug, Error)]
pub enum MqttError {
    #[error("MQTT connection failed: {0}")]
    Connection(String),
    #[error("MQTT publish failed: {0}")]
    Publish(String),
    #[error("MQTT subscribe failed: {0}")]
    Subscribe(String),
    #[error("MQTT client not connected")]
    NotConnected,
}

/// MQTT Quality of Service level.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Qos {
    AtMostOnce = 0,
    AtLeastOnce = 1,
    ExactlyOnce = 2,
}

/// A received MQTT message.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MqttMessage {
    pub topic: String,
    pub payload: String,
    pub qos: Qos,
    pub retained: bool,
}

/// Configuration for an MQTT client connection.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MqttConfig {
    pub broker: String,
    pub port: u16,
    pub client_id: String,
    pub username: Option<String>,
    pub password: Option<String>,
    pub keep_alive_secs: u16,
    pub last_will: Option<LastWill>,
}

/// Last Will and Testament message.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LastWill {
    pub topic: String,
    pub payload: String,
    pub qos: Qos,
    pub retain: bool,
}

impl Default for MqttConfig {
    fn default() -> Self {
        Self {
            broker: "localhost".to_string(),
            port: 1883,
            client_id: "halbert".to_string(),
            username: None,
            password: None,
            keep_alive_secs: 30,
            last_will: None,
        }
    }
}

/// Trait for MQTT client operations.
///
/// Implementations must handle auto-reconnect transparently. Callers
/// should not need to manage connection state.
#[async_trait]
pub trait MqttClient: Send + Sync {
    /// Connect to the broker using the provided configuration.
    async fn connect(&self, config: &MqttConfig) -> Result<(), MqttError>;

    /// Subscribe to a topic filter with the given QoS.
    async fn subscribe(&self, topic: &str, qos: Qos) -> Result<(), MqttError>;

    /// Unsubscribe from a topic filter.
    async fn unsubscribe(&self, topic: &str) -> Result<(), MqttError>;

    /// Publish a message to a topic.
    async fn publish(
        &self,
        topic: &str,
        payload: &str,
        qos: Qos,
        retain: bool,
    ) -> Result<(), MqttError>;

    /// Receive the next incoming message. Blocks until a message arrives.
    async fn recv(&self) -> Result<MqttMessage, MqttError>;

    /// Check if the client is currently connected.
    async fn is_connected(&self) -> bool;

    /// Disconnect from the broker.
    async fn disconnect(&self) -> Result<(), MqttError>;
}

/// Trait for an in-memory device state cache.
///
/// Maintains the last-known state of MQTT topics, updated by incoming
/// messages and retained messages. Used by the Python device registry
/// to query device state without re-subscribing.
pub trait DeviceStateCache: Send + Sync {
    /// Get the last-known payload for a topic, if any.
    fn get_state(&self, topic: &str) -> Option<String>;

    /// Update the state for a topic (called on incoming message).
    fn update_state(&self, topic: &str, payload: &str);

    /// Remove the state for a topic (called on device offline / LWT).
    fn remove_state(&self, topic: &str);

    /// List all topics currently in the cache.
    fn list_topics(&self) -> Vec<String>;

    /// Clear all cached state.
    fn clear(&self);
}

// Stub implementations (to be filled in R1.1/R1.2) ---------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mqtt_config_default() {
        let config = MqttConfig::default();
        assert_eq!(config.broker, "localhost");
        assert_eq!(config.port, 1883);
        assert_eq!(config.client_id, "halbert");
    }

    #[test]
    fn qos_serialization() {
        let qos = Qos::ExactlyOnce;
        let json = serde_json::to_string(&qos).unwrap();
        assert_eq!(json, r#""ExactlyOnce""#);
        let back: Qos = serde_json::from_str(&json).unwrap();
        assert_eq!(back, Qos::ExactlyOnce);
    }

    #[test]
    fn mqtt_message_serialization() {
        let msg = MqttMessage {
            topic: "zigbee2mqtt/living_room/light".to_string(),
            payload: r#"{"state":"ON","brightness":254}"#.to_string(),
            qos: Qos::AtLeastOnce,
            retained: false,
        };
        let json = serde_json::to_string(&msg).unwrap();
        let back: MqttMessage = serde_json::from_str(&json).unwrap();
        assert_eq!(back.topic, msg.topic);
        assert_eq!(back.payload, msg.payload);
    }
}
