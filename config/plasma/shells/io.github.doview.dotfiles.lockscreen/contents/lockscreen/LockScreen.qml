// SPDX-License-Identifier: MIT

import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import Qt5Compat.GraphicalEffects

import org.kde.breeze.components as Breeze
import org.kde.plasma.clock as PlasmaClock
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.networkmanagement as PlasmaNM
import org.kde.plasma.private.keyboardindicator as KeyboardIndicator
import org.kde.plasma.private.sessions
import org.kde.plasma.workspace.keyboardlayout as Keyboards
import org.kde.plasma.workspace.components as PW

Item {
    id: root

    // Properties and signals consumed by KScreenLocker.
    property bool debug: false
    property bool locked: true
    property bool viewVisible: false
    property bool suspendToRamSupported: false
    property bool suspendToDiskSupported: false
    property string notification: ""

    signal clearPassword()
    signal notificationRepeated()
    signal suspendToDisk()
    signal suspendToRam()

    readonly property bool activeView: !Window.window || Window.window.active
    readonly property color foreground: "#f7f8fa"
    readonly property string displayName: "Dovie Weinstock"
    readonly property string uiFont: "Segoe UI Variable"

    implicitWidth: 800
    implicitHeight: 600
    focus: true
    opacity: 0

    NumberAnimation {
        id: entranceFade
        target: root
        property: "opacity"
        from: 0
        to: 1
        duration: 220
        easing.type: Easing.OutCubic
    }

    LayoutMirroring.enabled: Application.layoutDirection === Qt.RightToLeft
    LayoutMirroring.childrenInherit: true

    SessionManagement {
        id: sessionManagement
    }

    KeyboardIndicator.KeyState {
        id: capsLockState
        key: Qt.Key_CapsLock
    }

    PlasmaNM.ConnectionIcon {
        id: networkState
    }

    PlasmaClock.Clock {
        id: clockSource
        trackSeconds: false
    }

    function focusPassword() {
        if (root.activeView && !keyboardMenu.visible && !powerMenu.visible) {
            passwordField.forceActiveFocus();
        }
    }

    onActiveViewChanged: {
        if (activeView) {
            Qt.callLater(focusPassword);
        }
    }
    onViewVisibleChanged: {
        if (viewVisible) {
            Qt.callLater(focusPassword);
        }
    }
    onLockedChanged: {
        if (locked && PasswordState.backend) {
            PasswordState.backend.startAuthenticating();
        }
    }

    Connections {
        target: PasswordState
        function onAuthenticated() { Qt.quit(); }
        function onPromptReadyChanged() { root.focusPassword(); }
    }

    Connections {
        target: root
        function onClearPassword() {
            PasswordState.clear();
            root.focusPassword();
        }
    }

    Connections {
        target: sessionManagement
        function onAboutToSuspend() { root.clearPassword(); }
    }

    FastBlur {
        anchors.fill: parent
        source: wallpaper
        radius: 24
        // GraphicalEffects cannot blur with Qt's software renderer. The
        // wallpaper and dark overlay still provide a usable fallback.
        visible: GraphicsInfo.api !== GraphicsInfo.Software
    }

    Rectangle {
        anchors.fill: parent
        color: "#000000"
        opacity: 0.28
    }

    MouseArea {
        id: interaction
        anchors.fill: parent
        onPressed: root.focusPassword()
    }

    // Escape clears a queued retry without putting another screen in front of
    // the field. Let KDE receive it too, preserving its screen-off behavior.
    Keys.onEscapePressed: event => {
        root.clearPassword();
        if (virtualKeyboard.keyboardActive) {
            virtualKeyboard.showHide();
        }
        event.accepted = false;
    }

    ColumnLayout {
        id: clock

        anchors.horizontalCenter: parent.horizontalCenter
        y: Math.max(24, parent.height * 0.16)
        spacing: 2
        opacity: 1

        PlasmaComponents3.Label {
            text: Qt.formatTime(clockSource.dateTime, "h:mm AP")
            color: root.foreground
            font.family: root.uiFont
            font.pixelSize: Math.max(72, Math.min(88, root.height * 0.09))
            font.weight: Font.DemiBold
            font.letterSpacing: -2
            renderType: Text.CurveRendering
            style: Text.Raised
            styleColor: "#66000000"
            Layout.alignment: Qt.AlignHCenter
        }

        PlasmaComponents3.Label {
            text: Qt.formatDate(clockSource.dateTime, Qt.locale(), Locale.LongFormat)
            color: root.foreground
            font.family: root.uiFont
            font.pixelSize: Math.max(20, Math.min(24, root.height * 0.027))
            font.weight: Font.Normal
            renderType: Text.CurveRendering
            style: Text.Raised
            styleColor: "#66000000"
            Layout.alignment: Qt.AlignHCenter
        }
    }

    Item {
        id: loginStack

        anchors.fill: parent

        Item {
            id: mainBlock
            anchors.fill: parent

            Rectangle {
                id: loginCard

                width: Math.min(420, Math.max(0, root.width - 32))
                height: loginContents.implicitHeight + 48
                anchors.horizontalCenter: parent.horizontalCenter
                y: Math.max(clock.y + clock.height + 16,
                    Math.min(parent.height - height - 72, parent.height * 0.48))
                radius: 16
                color: "#660d1117"

                ColumnLayout {
                    id: loginContents
                    anchors.fill: parent
                    anchors.margins: 24
                    spacing: 12

                    PlasmaComponents3.Label {
                        text: root.displayName
                        color: root.foreground
                        font.family: root.uiFont
                        font.pixelSize: 20
                        font.weight: Font.Medium
                        Layout.alignment: Qt.AlignHCenter
                    }

                    PlasmaComponents3.TextField {
                        id: passwordField
                        objectName: "passwordField"
                        focus: true
                        Accessible.name: placeholderText

                        Layout.fillWidth: true
                        Layout.preferredHeight: 48
                        font.family: root.uiFont
                        font.pixelSize: 16
                        leftPadding: 14
                        rightPadding: 14
                        topPadding: 10
                        bottomPadding: 10
                        color: root.foreground
                        placeholderTextColor: "#99ffffff"
                        selectionColor: "#55ffffff"
                        selectedTextColor: root.foreground
                        placeholderText: i18nd(
                            "plasma_shell_org.kde.plasma.desktop",
                            "Password"
                        )
                        echoMode: TextInput.Password
                        enabled: true
                        readOnly: PasswordState.submitting

                        background: Rectangle {
                            radius: 8
                            color: "#b30d1117"
                            border.width: passwordField.activeFocus ? 2 : 1
                            border.color: passwordField.activeFocus
                                ? "#e6ffffff"
                                : "#59ffffff"

                            Behavior on border.color {
                                ColorAnimation {
                                    duration: 100
                                }
                            }
                        }

                        onTextEdited: PasswordState.password = text
                        onAccepted: PasswordState.submit()
                        Keys.onPressed: event => {
                            // The Meta+L shortcut must not become password text.
                            if (event.modifiers & Qt.MetaModifier) {
                                event.accepted = true;
                            }
                        }

                        // Assigning text on clear destroys its binding. Keep an
                        // explicit Binding so all displays stay synchronized.
                        Binding {
                            target: passwordField
                            property: "text"
                            value: PasswordState.password
                            restoreMode: Binding.RestoreNone
                        }
                    }

                    PlasmaComponents3.Label {
                        id: statusMessage

                        text: {
                            const messages = [];
                            if (PasswordState.retrying && PasswordState.submitting) {
                                messages.push(i18nd("plasma_shell_org.kde.plasma.desktop", "Retrying…"));
                            } else if (PasswordState.submitting) {
                                messages.push(i18nd("plasma_shell_org.kde.plasma.desktop", "Unlocking…"));
                            } else if (PasswordState.message === "Unlocking failed") {
                                messages.push(i18nd("plasma_shell_org.kde.plasma.desktop", "Unlocking failed"));
                            } else if (PasswordState.message || root.notification) {
                                messages.push(PasswordState.message || root.notification);
                            }
                            if (capsLockState.locked) {
                                messages.push(i18nd("plasma_shell_org.kde.plasma.desktop", "Caps Lock is on"));
                            }
                            return messages.join("  •  ");
                        }
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        Layout.minimumHeight: implicitHeight

                        color: "#d9ffffff"
                        font.family: root.uiFont
                        font.pixelSize: 13
                        horizontalAlignment: Text.AlignHCenter
                        Layout.fillWidth: true
                    }
                }
            }
        }
    }

    Item {
        id: virtualKeyboard

        readonly property bool keyboardActive:
            Keyboards.KWinVirtualKeyboard.visible

        function showHide() {
            if (keyboardActive) {
                Qt.inputMethod.hide();
            } else {
                Keyboards.KWinVirtualKeyboard.enabled = true;
                Qt.inputMethod.show();
            }
            passwordField.forceActiveFocus();
        }
    }

    RowLayout {
        id: statusCluster

        anchors {
            right: parent.right
            bottom: parent.bottom
            margins: 18
        }
        spacing: 6

        Breeze.Battery {
            fontSize: 11
        }

        PlasmaComponents3.ToolButton {
            icon.name: networkState.connectionIcon || "network-disconnect"
            text: i18nd(
                "plasma_shell_org.kde.plasma.desktop",
                "Network status"
            )
            display: QQC2.AbstractButton.IconOnly
            enabled: false
        }

        PlasmaComponents3.ToolButton {
            icon.name: "preferences-desktop-accessibility"
            text: i18nd(
                "plasma_shell_org.kde.plasma.desktop",
                "Accessibility and keyboard"
            )
            display: QQC2.AbstractButton.IconOnly
            focusPolicy: Qt.TabFocus
            onClicked: keyboardMenu.open()

            QQC2.Menu {
                id: keyboardMenu
                y: -height
                onClosed: Qt.callLater(root.focusPassword)

                QQC2.MenuItem {
                    text: virtualKeyboard.keyboardActive
                        ? i18nd(
                            "plasma_shell_org.kde.plasma.desktop",
                            "Hide virtual keyboard"
                        )
                        : i18nd(
                            "plasma_shell_org.kde.plasma.desktop",
                            "Show virtual keyboard"
                        )
                    onTriggered: virtualKeyboard.showHide()
                }

                QQC2.MenuItem {
                    text: keyboardLayoutSwitcher.layoutNames.longName
                    visible: keyboardLayoutSwitcher.hasMultipleKeyboardLayouts
                    onTriggered:
                        keyboardLayoutSwitcher.keyboardLayout.switchToNextLayout()
                }
            }

            PW.KeyboardLayoutSwitcher {
                id: keyboardLayoutSwitcher
                anchors.fill: parent
                acceptedButtons: Qt.NoButton
            }
        }

        PlasmaComponents3.ToolButton {
            icon.name: "system-shutdown"
            text: i18nd(
                "plasma_shell_org.kde.plasma.desktop",
                "Power and session"
            )
            display: QQC2.AbstractButton.IconOnly
            focusPolicy: Qt.TabFocus
            onClicked: powerMenu.open()

            QQC2.Menu {
                id: powerMenu
                y: -height
                onClosed: Qt.callLater(root.focusPassword)

                QQC2.MenuItem {
                    text: i18nd(
                        "plasma_shell_org.kde.plasma.desktop",
                        "Sleep"
                    )
                    visible: root.suspendToRamSupported
                    onTriggered: root.suspendToRam()
                }

                QQC2.MenuItem {
                    text: i18nd(
                        "plasma_shell_org.kde.plasma.desktop",
                        "Hibernate"
                    )
                    visible: root.suspendToDiskSupported
                    onTriggered: root.suspendToDisk()
                }

                QQC2.MenuItem {
                    text: i18nd(
                        "plasma_shell_org.kde.plasma.desktop",
                        "Switch User"
                    )
                    visible: sessionManagement.canSwitchUser
                    onTriggered: sessionManagement.switchUser()
                }
            }
        }
    }

    Component.onCompleted: {
        PasswordState.initialize(authenticator);
        entranceFade.start();
        Qt.callLater(root.focusPassword);
    }
}
