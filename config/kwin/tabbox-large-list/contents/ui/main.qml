/*
 * Derived from KDE's Compact KWin task switcher.
 *
 * SPDX-FileCopyrightText: 2011 Martin Gräßlin <mgraesslin@kde.org>
 * SPDX-FileCopyrightText: 2026 DovieW
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import org.kde.ksvg as KSvg
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kwin as KWin

KWin.TabBoxSwitcher {
    id: tabBox
    currentIndex: windowList.currentIndex

    function itemCaption(caption, minimized) {
        return minimized ? "(" + caption + ")" : caption;
    }

    TextMetrics {
        id: textMetrics
        property string longestCaption: tabBox.model?.longestCaption() || placeholderLabel.text
        text: itemCaption(longestCaption, true)
        font.bold: true
        font.pointSize: Kirigami.Theme.defaultFont.pointSize + 2
    }

    onVisibleChanged: {
        if (visible) {
            textMetrics.longestCaption = tabBox.model?.longestCaption() || placeholderLabel.text;
        }
    }
    onModelChanged: {
        textMetrics.longestCaption = tabBox.model?.longestCaption() || placeholderLabel.text;
    }

    Timer {
        id: activationTimer
        interval: Kirigami.Units.shortDuration
        onTriggered: tabBox.model.activate(windowList.currentIndex)
    }

    PlasmaCore.Dialog {
        id: dialog
        location: PlasmaCore.Types.Floating
        visible: tabBox.visible
        flags: Qt.Popup | Qt.X11BypassWindowManagerHint
        x: tabBox.screenGeometry.x + tabBox.screenGeometry.width * 0.5 - dialogMainItem.width * 0.5
        y: tabBox.screenGeometry.y + tabBox.screenGeometry.height * 0.5 - dialogMainItem.height * 0.5

        mainItem: Item {
            id: dialogMainItem

            property int optimalWidth: textMetrics.width
                + Kirigami.Units.iconSizes.medium
                + 4 * Kirigami.Units.smallSpacing
                + hoverItem.margins.right
                + hoverItem.margins.left
            property int optimalHeight: windowList.rowHeight * (windowList.count || 1)
            width: Math.min(
                Math.max(tabBox.screenGeometry.width * 0.32, optimalWidth),
                tabBox.screenGeometry.width * 0.7
            )
            height: Math.min(optimalHeight, tabBox.screenGeometry.height * 0.8)

            KSvg.FrameSvgItem {
                id: hoverItem
                imagePath: "widgets/viewitem"
                prefix: "hover"
                visible: false
            }

            ListView {
                id: windowList

                property int rowHeight: Math.max(
                    Kirigami.Units.iconSizes.medium + 2 * Kirigami.Units.smallSpacing,
                    textMetrics.height + hoverItem.margins.top + hoverItem.margins.bottom
                )

                anchors.fill: parent
                clip: true
                focus: true
                model: tabBox.model

                delegate: RowLayout {
                    width: windowList.width
                    height: windowList.rowHeight
                    opacity: minimized ? 0.75 : 1.0
                    spacing: 2 * Kirigami.Units.smallSpacing

                    Accessible.name: captionItem.text

                    Kirigami.Icon {
                        source: model.icon
                        Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                        Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                        Layout.leftMargin: hoverItem.margins.left
                    }

                    PlasmaComponents3.Label {
                        id: captionItem
                        horizontalAlignment: Text.AlignLeft
                        verticalAlignment: Text.AlignVCenter
                        text: itemCaption(caption, minimized)
                        textFormat: Text.PlainText
                        font.pointSize: Kirigami.Theme.defaultFont.pointSize + 2
                        font.weight: index === windowList.currentIndex ? Font.Bold : Font.Normal
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                        Layout.rightMargin: hoverItem.margins.right
                        Layout.topMargin: hoverItem.margins.top
                        Layout.bottomMargin: hoverItem.margins.bottom
                    }

                    TapHandler {
                        onTapped: {
                            windowList.currentIndex = index;
                            activationTimer.start();
                        }
                    }
                }

                highlight: KSvg.FrameSvgItem {
                    imagePath: "widgets/viewitem"
                    prefix: "hover"
                    width: windowList.width
                }
                highlightMoveDuration: 0
                highlightResizeDuration: 0
                boundsBehavior: Flickable.StopAtBounds

                Connections {
                    target: tabBox
                    function onCurrentIndexChanged() {
                        windowList.currentIndex = tabBox.currentIndex;
                    }
                }

                RowLayout {
                    visible: windowList.count === 0
                    anchors.centerIn: parent
                    spacing: 2 * Kirigami.Units.smallSpacing

                    Kirigami.Icon {
                        source: "edit-none"
                        Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                        Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                    }
                    PlasmaComponents3.Label {
                        id: placeholderLabel
                        text: i18ndc(
                            "kwin",
                            "@info:placeholder no entries in the task switcher",
                            "No open windows"
                        )
                        font.pointSize: Kirigami.Theme.defaultFont.pointSize + 2
                    }
                }
            }

            Keys.onPressed: event => {
                if (event.key === Qt.Key_Up || event.key === Qt.Key_Left) {
                    if (windowList.currentIndex === 0) {
                        windowList.currentIndex = windowList.count - 1;
                    } else {
                        windowList.decrementCurrentIndex();
                    }
                } else if (event.key === Qt.Key_Down || event.key === Qt.Key_Right) {
                    if (windowList.currentIndex === windowList.count - 1) {
                        windowList.currentIndex = 0;
                    } else {
                        windowList.incrementCurrentIndex();
                    }
                }
            }
        }

        onSceneGraphError: () => {}
    }
}
