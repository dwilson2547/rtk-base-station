/*
  RTK Base Station — shared ArduinoOTA helper

  Network firmware updates for the roof-mounted ESP32, so the board can be
  reflashed without physical access — e.g. swapping between this Phase 1 raw
  logger ("publish" mode, for a re-survey) and the Phase 3 NTRIP caster.

  CRITICAL: every roof firmware MUST include this and call otaBegin()/otaLoop().
  OTA only exists in the firmware that is *currently running*. Flash a build that
  lacks it and you are back on the roof with a USB cable. The Phase 3 caster keeps
  its own copy of this file — keep the two in sync if you ever change it.

  Assumes WiFi (STA) is already connected before otaBegin() is called.
  ArduinoOTA is part of the ESP32 Arduino core — no extra library to install.

  Usage:
    #include "ota.h"
    ...
    connectWiFi();
    otaBegin("rtk-base-logger");   // distinct name per mode; see it via avahi-browse
    ...
    void loop() { otaLoop(); ... }
*/
#pragma once

#include <ArduinoOTA.h>

// OTA upload password — required to push firmware, protects the endpoint on the
// LAN. Replace before flashing. NEVER commit a real value. Can also be supplied
// at build time with -DOTA_PASSWORD="..." to keep it out of the source entirely.
#ifndef OTA_PASSWORD
#define OTA_PASSWORD "YOUR_OTA_PASSWORD"
#endif

inline void otaBegin(const char* hostname) {
  // Hostname is what identifies the unit on the network — pick a name per mode
  // (rtk-base-logger vs rtk-base-ntrip) so `avahi-browse -rt _arduino._tcp`
  // tells you at a glance which firmware is currently on the roof.
  ArduinoOTA.setHostname(hostname);
  ArduinoOTA.setPassword(OTA_PASSWORD);

  ArduinoOTA.onStart([]() {
    // During an upload the main loop is blocked; for the logger that means a
    // brief capture gap, for the caster a momentary corrections dropout. Fine.
    Serial.println("\n[OTA] update starting — main loop paused");
  });
  ArduinoOTA.onProgress([](unsigned int prog, unsigned int total) {
    Serial.printf("[OTA] %u%%\r", total ? (prog * 100) / total : 0);
  });
  ArduinoOTA.onEnd([]() {
    Serial.println("\n[OTA] complete — rebooting into new firmware");
  });
  ArduinoOTA.onError([](ota_error_t err) {
    Serial.printf("[OTA] error %u — update aborted, old firmware kept\n", err);
  });

  ArduinoOTA.begin();   // also brings up mDNS for discovery
  Serial.printf("[OTA] ready as '%s.local' — push with arduino-cli --upload --port <ip>\n",
                hostname);
}

inline void otaLoop() {
  ArduinoOTA.handle();
}
