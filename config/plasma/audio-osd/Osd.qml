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

    function outputIcon(volumeIcon, output) {
        if (!/^audio-volume-(low|medium|high)$/.test(volumeIcon) || !output) {
            return volumeIcon;
        }

        const deviceIcon = output.properties?.["device.icon_name"] ?? "";
        const form = output.formFactor ?? "";
        if (form === "headset" || deviceIcon.startsWith("audio-headset")) {
            return "audio-headset-symbolic";
        }
        if (form === "headphone" || deviceIcon.startsWith("audio-headphones")) {
            return "audio-headphones-symbolic";
        }
        if (deviceIcon === "video-display" || /hdmi/i.test(output.name ?? "")) {
            return "video-display";
        }
        if (form === "speaker" || deviceIcon.startsWith("audio-speakers")) {
            return "audio-speakers-symbolic";
        }
        return volumeIcon;
    }

    width: Math.max(Math.min(Screen.desktopAvailableWidth / 2, mainItem.implicitWidth), Kirigami.Units.gridUnit * 15) + leftPadding + rightPadding
    height: mainItem.implicitHeight + topPadding + bottomPadding

    mainItem: OsdItem {
        id: osd
        icon: root.outputIcon(root.icon, Audio.PreferredDevice.sink)
    }
}
