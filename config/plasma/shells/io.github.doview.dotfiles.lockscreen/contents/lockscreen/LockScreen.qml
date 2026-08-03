// SPDX-License-Identifier: MIT

import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import Qt5Compat.GraphicalEffects

import org.kde.breeze.components as Breeze
import org.kde.kirigami as Kirigami
import org.kde.kscreenlocker as ScreenLocker
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

    readonly property bool activeView:
        (Window.window && Window.window.active) || interaction.containsMouse
    readonly property bool loginVisible: interaction.uiVisible && activeView
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

    Connections {
        target: authenticator

        function onFailed(kind) {
            if (kind === 0) {
                root.notification = i18nd(
                    "plasma_shell_org.kde.plasma.desktop",
                    "Unlocking failed"
                );
                PasswordState.password = "";
                passwordField.text = "";
                passwordField.forceActiveFocus();
                graceLockTimer.restart();
                messageTimer.restart();
                rejectAnimation.restart();
            }
        }

        function onSucceeded() {
            Qt.quit();
        }

        function onInfoMessageChanged() {
            root.notification = authenticator.infoMessage;
        }

        function onErrorMessageChanged() {
            root.notification = authenticator.errorMessage;
        }

        function onPromptChanged(message) {
            root.notification = message;
        }

        function onPromptForSecretChanged() {
            interaction.reveal();
            passwordField.forceActiveFocus();
        }
    }

    Connections {
        target: root

        function onClearPassword() {
            PasswordState.password = "";
            passwordField.text = "";
            passwordField.forceActiveFocus();
        }
    }

    FastBlur {
        anchors.fill: parent
        source: wallpaper
        radius: root.loginVisible ? 42 : 0
        opacity: root.loginVisible ? 1 : 0

        Behavior on radius {
            NumberAnimation {
                duration: 180
                easing.type: Easing.OutCubic
            }
        }

        Behavior on opacity {
            NumberAnimation {
                duration: 160
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        color: "#000000"
        opacity: root.loginVisible ? 0.32 : 0.08

        Behavior on opacity {
            NumberAnimation {
                duration: 180
                easing.type: Easing.OutCubic
            }
        }
    }

    MouseArea {
        id: interaction

        property bool uiVisible: false
        property bool pointerMoved: false

        function reveal() {
            uiVisible = true;
            fadeTimer.restart();
            authenticator.startAuthenticating();
            passwordField.forceActiveFocus();
        }

        anchors.fill: parent
        hoverEnabled: true
        cursorShape: uiVisible ? Qt.ArrowCursor : Qt.BlankCursor

        onPressed: reveal()
        onPositionChanged: {
            if (pointerMoved) {
                reveal();
            }
            pointerMoved = true;
        }
        onExited: {
            if (!PasswordState.password) {
                uiVisible = false;
            }
        }

        Keys.onEscapePressed: {
            PasswordState.password = "";
            passwordField.text = "";
            uiVisible = false;
            if (virtualKeyboard.keyboardActive) {
                virtualKeyboard.showHide();
            }
        }

        Keys.onPressed: event => {
            reveal();
            event.accepted = false;
        }

        Timer {
            id: fadeTimer
            interval: 10000
            onTriggered: {
                if (!PasswordState.password && !virtualKeyboard.keyboardActive) {
                    interaction.uiVisible = false;
                }
            }
        }
    }

    ColumnLayout {
        id: clock

        anchors.horizontalCenter: parent.horizontalCenter
        y: Math.max(52, parent.height * 0.18)
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

    QQC2.StackView {
        id: loginStack

        anchors.fill: parent
        focus: true

        initialItem: Item {
            id: mainBlock

            property int visibleBoundary: loginCard.y + loginCard.height

            Item {
                id: loginCard

                width: Math.max(360, Math.min(420, root.width - 48))
                height: 196
                anchors.horizontalCenter: parent.horizontalCenter
                y: Math.min(parent.height - height - 84, parent.height * 0.49)
                opacity: root.loginVisible ? 1 : 0
                enabled: root.loginVisible
                visible: opacity > 0

                Behavior on opacity {
                    NumberAnimation {
                        duration: 170
                    }
                }

                ColumnLayout {
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
                        enabled: !authenticator.graceLocked
                        text: PasswordState.password

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

                        onTextEdited: {
                            PasswordState.password = text;
                            fadeTimer.restart();
                        }

                        onAccepted: {
                            fadeTimer.stop();
                            authenticator.respond(text);
                        }
                    }

                    PlasmaComponents3.Label {
                        id: statusMessage

                        text: {
                            if (capsLockState.locked && root.notification) {
                                return root.notification + "  •  "
                                    + i18nd(
                                        "plasma_shell_org.kde.plasma.desktop",
                                        "Caps Lock is on"
                                    );
                            }
                            if (capsLockState.locked) {
                                return i18nd(
                                    "plasma_shell_org.kde.plasma.desktop",
                                    "Caps Lock is on"
                                );
                            }
                            if (root.notification) {
                                return root.notification;
                            }
                            return "";
                        }
                        color: "#d9ffffff"
                        font.family: root.uiFont
                        font.pixelSize: 13
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                        Layout.fillWidth: true

                        SequentialAnimation {
                            id: rejectAnimation

                            NumberAnimation {
                                target: statusMessage
                                property: "opacity"
                                from: 1
                                to: 0.25
                                duration: 80
                            }
                            NumberAnimation {
                                target: statusMessage
                                property: "opacity"
                                from: 0.25
                                to: 1
                                duration: 120
                            }
                        }
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
        opacity: root.loginVisible ? 1 : 0
        visible: opacity > 0

        Behavior on opacity {
            NumberAnimation {
                duration: 160
            }
        }

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
            focusPolicy: Qt.TabFocus
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

    Timer {
        id: graceLockTimer
        interval: 3000
        onTriggered: {
            root.clearPassword();
            authenticator.startAuthenticating();
        }
    }

    Timer {
        id: messageTimer
        interval: 3000
        onTriggered: root.notification = ""
    }

    Component.onCompleted: {
        entranceFade.start();
        interaction.forceActiveFocus();
        authenticator.startAuthenticating();
    }
}
