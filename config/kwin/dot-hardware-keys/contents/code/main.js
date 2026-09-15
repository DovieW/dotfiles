function adjustScreenBrightness(direction) {
    callDBus(
        "org.kde.Solid.PowerManagement",
        "/org/kde/Solid/PowerManagement/Actions/BrightnessControl",
        "org.kde.Solid.PowerManagement.Actions.BrightnessControl",
        "brightnessMax",
        function (maximum) {
            callDBus(
                "org.kde.Solid.PowerManagement",
                "/org/kde/Solid/PowerManagement/Actions/BrightnessControl",
                "org.kde.Solid.PowerManagement.Actions.BrightnessControl",
                "brightness",
                function (current) {
                    var target = Math.max(
                        0,
                        Math.min(maximum, current + direction * maximum / 10)
                    );
                    callDBus(
                        "org.kde.Solid.PowerManagement",
                        "/org/kde/Solid/PowerManagement/Actions/BrightnessControl",
                        "org.kde.Solid.PowerManagement.Actions.BrightnessControl",
                        "setBrightness",
                        Math.round(target)
                    );
                }
            );
        }
    );
}

registerShortcut(
    "dot-brightness-down",
    "Decrease Screen Brightness by 10%",
    "Monitor Brightness Down",
    function () { adjustScreenBrightness(-1); }
);

registerShortcut(
    "dot-brightness-up",
    "Increase Screen Brightness by 10%",
    "Monitor Brightness Up",
    function () { adjustScreenBrightness(1); }
);
