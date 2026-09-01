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

// ---------------------------------------------------------------------------
// Implementations
// ---------------------------------------------------------------------------

use rumqttc::{AsyncClient, MqttOptions, QoS as RumqttQos};
use std::sync::Arc;
use tokio::sync::Mutex;
use tokio::sync::mpsc;

/// Convert our Qos enum to rumqttc's QoS enum.
fn to_rumqtt_qos(qos: Qos) -> RumqttQos {
    match qos {
        Qos::AtMostOnce => RumqttQos::AtMostOnce,
        Qos::AtLeastOnce => RumqttQos::AtLeastOnce,
        Qos::ExactlyOnce => RumqttQos::ExactlyOnce,
    }
}

/// Convert rumqttc's QoS enum to ours.
fn from_rumqtt_qos(qos: RumqttQos) -> Qos {
    match qos {
        RumqttQos::AtMostOnce => Qos::AtMostOnce,
        RumqttQos::AtLeastOnce => Qos::AtLeastOnce,
        RumqttQos::ExactlyOnce => Qos::ExactlyOnce,
    }
}

/// MQTT client implementation backed by `rumqttc`.
///
/// Uses an internal channel to bridge rumqttc's event loop into our
/// `recv()` interface. Auto-reconnect is handled by rumqttc's built-in
/// connection management.
pub struct RumqttClient {
    /// The rumqttc async client handle.
    client: Mutex<Option<AsyncClient>>,
    /// Channel receiver for incoming messages from the event loop.
    rx: Mutex<mpsc::Receiver<MqttMessage>>,
    /// Channel sender for incoming messages (cloned into the event loop task).
    tx: mpsc::Sender<MqttMessage>,
    /// Connection state.
    connected: Arc<std::sync::atomic::AtomicBool>,
}

impl RumqttClient {
    /// Create a new client. Does not connect — call `connect()` to establish
    /// a connection to the broker.
    pub fn new() -> Self {
        let (tx, rx) = mpsc::channel(256);
        Self {
            client: Mutex::new(None),
            rx: Mutex::new(rx),
            tx,
            connected: Arc::new(std::sync::atomic::AtomicBool::new(false)),
        }
    }
}

impl Default for RumqttClient {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl MqttClient for RumqttClient {
    async fn connect(&self, config: &MqttConfig) -> Result<(), MqttError> {
        let mut opts = MqttOptions::new(
            &config.client_id,
            &config.broker,
            config.port,
        );
        opts.set_keep_alive(std::time::Duration::from_secs(
            config.keep_alive_secs as u64,
        ));

        if let (Some(user), Some(pass)) = (&config.username, &config.password) {
            opts.set_credentials(user, pass);
        }

        if let Some(lwt) = &config.last_will {
            opts.set_last_will(
                rumqttc::LastWill {
                    topic: lwt.topic.clone(),
                    message: lwt.payload.clone().into(),
                    qos: to_rumqtt_qos(lwt.qos),
                    retain: lwt.retain,
                },
            );
        }

        // rumqttc 0.25: auto-reconnect is configured via MqttOptions, not EventLoop.
        // The event loop will retry connections automatically when the broker drops.
        let (client, mut event_loop) = AsyncClient::new(opts, 10);

        // Spawn a task to poll the event loop and forward Publish events
        // to our channel. This bridges rumqttc's poll-based API into our
        // channel-based recv() interface.
        let tx = self.tx.clone();
        let connected = self.connected.clone();
        tokio::spawn(async move {
            loop {
                match event_loop.poll().await {
                    Ok(rumqttc::Event::Incoming(rumqttc::Packet::Publish(p))) => {
                        let payload = String::from_utf8_lossy(&p.payload).to_string();
                        let msg = MqttMessage {
                            topic: p.topic,
                            payload,
                            qos: from_rumqtt_qos(p.qos),
                            retained: p.retain,
                        };
                        if tx.send(msg).await.is_err() {
                            // Receiver dropped — client was dropped. Stop polling.
                            connected.store(false, std::sync::atomic::Ordering::Relaxed);
                            break;
                        }
                    }
                    Ok(_) => {
                        // Other events (ConnAck, SubAck, etc.) — update connected state.
                        connected.store(true, std::sync::atomic::Ordering::Relaxed);
                    }
                    Err(e) => {
                        tracing::warn!("MQTT event loop error: {} (auto-reconnecting)", e);
                        // rumqttc with set_auto_reconnect(true) will retry.
                        // We keep polling; the next Ok event will reset connected.
                        connected.store(false, std::sync::atomic::Ordering::Relaxed);
                    }
                }
            }
        });

        *self.client.lock().await = Some(client);
        Ok(())
    }

    async fn subscribe(&self, topic: &str, qos: Qos) -> Result<(), MqttError> {
        let guard = self.client.lock().await;
        let client = guard.as_ref().ok_or(MqttError::NotConnected)?;
        client
            .subscribe(topic, to_rumqtt_qos(qos))
            .await
            .map_err(|e| MqttError::Subscribe(e.to_string()))
    }

    async fn unsubscribe(&self, topic: &str) -> Result<(), MqttError> {
        let guard = self.client.lock().await;
        let client = guard.as_ref().ok_or(MqttError::NotConnected)?;
        client
            .unsubscribe(topic)
            .await
            .map_err(|e| MqttError::Subscribe(e.to_string()))
    }

    async fn publish(
        &self,
        topic: &str,
        payload: &str,
        qos: Qos,
        retain: bool,
    ) -> Result<(), MqttError> {
        let guard = self.client.lock().await;
        let client = guard.as_ref().ok_or(MqttError::NotConnected)?;
        client
            .publish(topic, to_rumqtt_qos(qos), retain, payload)
            .await
            .map_err(|e| MqttError::Publish(e.to_string()))
    }

    async fn recv(&self) -> Result<MqttMessage, MqttError> {
        let mut rx = self.rx.lock().await;
        rx.recv()
            .await
            .ok_or(MqttError::NotConnected)
    }

    async fn is_connected(&self) -> bool {
        self.connected
            .load(std::sync::atomic::Ordering::Relaxed)
    }

    async fn disconnect(&self) -> Result<(), MqttError> {
        let mut guard = self.client.lock().await;
        if let Some(client) = guard.take() {
            // rumqttc AsyncClient doesn't have an explicit disconnect method,
            // but dropping the client cancels the connection.
            drop(client);
        }
        self.connected
            .store(false, std::sync::atomic::Ordering::Relaxed);
        Ok(())
    }
}

/// In-memory device state cache backed by `DashMap`.
///
/// Thread-safe, lock-free reads. Used by the Python device registry to
/// query the last-known state of MQTT topics without re-subscribing.
pub struct InMemoryDeviceStateCache {
    states: dashmap::DashMap<String, String>,
}

impl InMemoryDeviceStateCache {
    pub fn new() -> Self {
        Self {
            states: dashmap::DashMap::new(),
        }
    }
}

impl Default for InMemoryDeviceStateCache {
    fn default() -> Self {
        Self::new()
    }
}

impl DeviceStateCache for InMemoryDeviceStateCache {
    fn get_state(&self, topic: &str) -> Option<String> {
        self.states.get(topic).map(|v| v.clone())
    }

    fn update_state(&self, topic: &str, payload: &str) {
        self.states.insert(topic.to_string(), payload.to_string());
    }

    fn remove_state(&self, topic: &str) {
        self.states.remove(topic);
    }

    fn list_topics(&self) -> Vec<String> {
        self.states.iter().map(|kv| kv.key().clone()).collect()
    }

    fn clear(&self) {
        self.states.clear();
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

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

    #[test]
    fn device_state_cache_basic() {
        let cache = InMemoryDeviceStateCache::new();
        assert!(cache.get_state("sensor/temp").is_none());

        cache.update_state("sensor/temp", "22.5");
        assert_eq!(cache.get_state("sensor/temp").unwrap(), "22.5");

        cache.update_state("sensor/humidity", "45");
        assert_eq!(cache.list_topics().len(), 2);

        cache.remove_state("sensor/temp");
        assert!(cache.get_state("sensor/temp").is_none());
        assert_eq!(cache.list_topics().len(), 1);

        cache.clear();
        assert!(cache.list_topics().is_empty());
    }

    #[test]
    fn qos_conversion_roundtrip() {
        assert_eq!(to_rumqtt_qos(Qos::AtMostOnce), RumqttQos::AtMostOnce);
        assert_eq!(to_rumqtt_qos(Qos::AtLeastOnce), RumqttQos::AtLeastOnce);
        assert_eq!(to_rumqtt_qos(Qos::ExactlyOnce), RumqttQos::ExactlyOnce);

        assert_eq!(from_rumqtt_qos(RumqttQos::AtMostOnce), Qos::AtMostOnce);
        assert_eq!(from_rumqtt_qos(RumqttQos::AtLeastOnce), Qos::AtLeastOnce);
        assert_eq!(from_rumqtt_qos(RumqttQos::ExactlyOnce), Qos::ExactlyOnce);
    }

    #[test]
    fn rumqtt_client_creation() {
        let client = RumqttClient::new();
        // Should not be connected before connect() is called.
        // (is_connected is async, so we check the atomic directly)
        assert!(!client
            .connected
            .load(std::sync::atomic::Ordering::Relaxed));
    }
}
