/*
    SPDX-FileCopyrightText: 2014 Martin Klapetek <mklapetek@kde.org>
    SPDX-FileCopyrightText: 2026 David Edmundson <davidedmundson@kde.org>

    SPDX-License-Identifier: GPL-2.0-or-later
*/

import QtQuick
import org.kde.kirigami as Kirigami
import org.kde.plasma.private.volume as Audio

OsdWindow {
    id: root

    LayoutMirroring.enabled: Application.layoutDirection === Qt.RightToLeft
    LayoutMirroring.childrenInherit: true

    property alias timeout: osd.timeout
    property alias osdValue: osd.osdValue
    property alias osdMaxValue: osd.osdMaxValue
    property alias osdAdditionalText: osd.osdAdditionalText
    property alias showingProgress: osd.showingProgress
    property string icon
    readonly property bool showingOutputVolume: visible && showingProgress
        && /^audio-volume-(low|medium|high(?:-warning|-danger)?)$/.test(icon)
    property real volumeFill: 0

    onShowingOutputVolumeChanged: {
        fillAnimation.stop();
        if (showingOutputVolume) {
            volumeFill = osd.progressTarget;
        }
    }

    function updateVolumeFill() {
        if (!showingOutputVolume || volumeFill === osd.progressTarget) {
            return;
        }
        fillAnimation.stop();
        fillAnimation.from = volumeFill;
        fillAnimation.to = osd.progressTarget;
        fillAnimation.start();
    }

    NumberAnimation {
        id: fillAnimation
        target: root
        property: "volumeFill"
        duration: 85
        easing.type: Easing.OutCubic
    }

    function outputIcon(volumeIcon, output) {
        if (!/^audio-volume-(low|medium|high)$/.test(volumeIcon) || !output) {
            return volumeIcon;
        }

        const properties = output.properties ?? {};
        const deviceIcon = properties["device.icon_name"] ?? output.iconName ?? "";
        const form = (output.formFactor ?? "").toLowerCase();
        const port = output.ports?.[output.activePortIndex]?.name ?? "";
        // Bluetooth stereo can report the same headset port as call audio.
        if (/^a2dp(?:[-_]|$)/.test(properties["api.bluez5.profile"] ?? "")) {
            return deviceIcon.startsWith("audio-speakers") || form === "speaker"
                ? "audio-speakers-symbolic" : "audio-headphones-symbolic";
        }
        // A laptop sink may expose both speakers and a headphone jack.
        if (/headset/i.test(port)) {
            return "audio-headset-symbolic";
        }
        if (/headphone/i.test(port)) {
            return "audio-headphones-symbolic";
        }
        if (deviceIcon.startsWith("video-display") || /hdmi|displayport/i.test(port + " " + (output.name ?? ""))) {
            return "video-display";
        }
        if (/speaker|line[-_ ]?out/i.test(port)) {
            return "audio-speakers-symbolic";
        }
        if (form === "headset" || deviceIcon.startsWith("audio-headset")) {
            return "audio-headset-symbolic";
        }
        if (["headphone", "headphones"].includes(form) || deviceIcon.startsWith("audio-headphones")) {
            return "audio-headphones-symbolic";
        }
        if (form === "speaker" || deviceIcon.startsWith("audio-speakers")) {
            return "audio-speakers-symbolic";
        }
        if (properties["device.bus"] === "usb" || /spdif|s\/pdif|iec958/i.test(port)) {
            return "audio-card-symbolic";
        }
        return volumeIcon;
    }

    width: Math.max(Math.min(Screen.desktopAvailableWidth / 2, mainItem.implicitWidth), Kirigami.Units.gridUnit * 15) + leftPadding + rightPadding
    height: mainItem.implicitHeight + topPadding + bottomPadding

    mainItem: OsdItem {
        id: osd
        icon: root.outputIcon(root.icon, Audio.PreferredDevice.sink)
        barProgress: root.showingOutputVolume ? root.volumeFill : progressTarget
        // Plasma sets the value and icon in sequence.
        onProgressTargetChanged: Qt.callLater(root.updateVolumeFill)
    }
}
