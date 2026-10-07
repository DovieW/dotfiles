import QtQuick
import QtTest
import "../../config/plasma/shells/io.github.doview.dotfiles.lockscreen/contents/lockscreen" as Managed

Item {
    id: harness
    width: 800
    height: 600

    function i18nd(domain, text) { return text; }

    property QtObject authenticator: QtObject {
        property int starts: 0
        property var responses: []
        property string prompt: ""
        property string promptForSecret: ""
        property string infoMessage: ""
        property string errorMessage: ""
        signal failed(int kind)
        signal succeeded()
        signal loginFailedDelayStarted(int kind, var source, int microseconds)

        function startAuthenticating() { starts++; }
        function respond(password) { responses = responses.concat([password]); }
    }

    Rectangle {
        id: wallpaper
        anchors.fill: parent
        color: "#284536"
    }

    Managed.LockScreen {
        id: screen
        anchors.fill: parent
        viewVisible: true
    }

    // KScreenLocker creates multiple roots in a shared engine.
    Managed.LockScreen {
        id: secondScreen
        width: 800
        height: 600
        visible: false
    }

    TestCase {
        name: "ManagedLockScreen"
        when: windowShown

        property var field
        property var secondField

        function initTestCase() {
            field = findChild(screen, "passwordField");
            secondField = findChild(secondScreen, "passwordField");
            verify(field !== null);
            verify(secondField !== null);
            compare(authenticator.starts, 1);
        }

        function init() {
            Managed.PasswordState.retryTimer.stop();
            Managed.PasswordState.clear();
            Managed.PasswordState.submitting = false;
            Managed.PasswordState.promptReady = false;
            Managed.PasswordState.retryNotBefore = 0;
            Managed.PasswordState.message = "";
            authenticator.responses = [];
            screen.focusPassword();
        }

        function test_first_key_and_persistent_input() {
            tryCompare(field, "activeFocus", true);
            keyClick(Qt.Key_L, Qt.MetaModifier);
            compare(field.text, "");
            keyClick(Qt.Key_A);
            compare(field.text, "a");
            compare(secondField.text, "a");
            keyClick(Qt.Key_Escape);
            compare(field.text, "");
            compare(secondField.text, "");
            verify(field.visible);
            verify(field.activeFocus);
            mouseMove(screen, -20, -20);
            wait(10100);
            verify(field.visible);
            keyClick(Qt.Key_B);
            compare(field.text, "b");
            compare(secondField.text, "b");
        }

        function test_queue_until_prompt_and_ignore_duplicate_enter() {
            Managed.PasswordState.password = "test-secret";
            keyClick(Qt.Key_Return);
            compare(authenticator.responses.length, 0);
            verify(Managed.PasswordState.queued);
            keyClick(Qt.Key_Return);
            authenticator.promptForSecretChanged();
            compare(authenticator.responses.length, 1);
            compare(authenticator.responses[0], "test-secret");
            compare(field.text, "");
            compare(secondField.text, "");
            compare(Managed.PasswordState.queuedPassword, "");
            keyClick(Qt.Key_Return);
            compare(authenticator.responses.length, 1);
        }

        function test_failed_password_allows_typing_and_queued_retry() {
            authenticator.promptForSecretChanged();
            Managed.PasswordState.password = "wrong";
            keyClick(Qt.Key_Return);
            authenticator.failed(0);
            verify(!field.readOnly);
            compare(field.text, "");
            compare(Managed.PasswordState.message, "Unlocking failed");
            keyClick(Qt.Key_C);
            keyClick(Qt.Key_Return);
            compare(authenticator.responses.length, 1);
            verify(Managed.PasswordState.queued);
            const starts = authenticator.starts;
            tryCompare(authenticator, "starts", starts + 1, 4000);
            // Restarting PAM is not enough: the new prompt must arrive.
            compare(authenticator.responses.length, 1);
            authenticator.promptForSecretChanged();
            compare(authenticator.responses.length, 2);
            compare(authenticator.responses[1], "c");
        }

        function test_escape_cancels_queued_secret() {
            authenticator.failed(0);
            Managed.PasswordState.password = "queued-secret";
            keyClick(Qt.Key_Return);
            keyClick(Qt.Key_Escape);
            verify(!Managed.PasswordState.queued);
            verify(!Managed.PasswordState.submitting);
            compare(Managed.PasswordState.queuedPassword, "");
            authenticator.promptForSecretChanged();
            compare(authenticator.responses.length, 0);
            verify(field.visible);
        }

        function test_clear_keeps_display_bindings() {
            Managed.PasswordState.password = "before";
            screen.clearPassword();
            compare(field.text, "");
            Managed.PasswordState.password = "after";
            compare(field.text, "after");
            compare(secondField.text, "after");
        }

        function test_next_pam_prompt_accepts_second_factor() {
            authenticator.promptForSecretChanged();
            Managed.PasswordState.password = "first-factor";
            keyClick(Qt.Key_Return);
            verify(field.readOnly);
            authenticator.prompt = "Verification code";
            verify(!field.readOnly);
            Managed.PasswordState.password = "second-factor";
            keyClick(Qt.Key_Return);
            compare(authenticator.responses.length, 2);
            compare(authenticator.responses[1], "second-factor");
        }

        function test_pam_delay_and_noninteractive_failure() {
            authenticator.loginFailedDelayStarted(0, null, 6000000);
            authenticator.failed(0);
            verify(Managed.PasswordState.retryTimer.interval > 5900);
            Managed.PasswordState.retryTimer.stop();
            Managed.PasswordState.password = "keep";
            authenticator.failed(1);
            compare(Managed.PasswordState.password, "keep");
            verify(!Managed.PasswordState.retryTimer.running);
        }

        function test_small_display() {
            harness.width = 360;
            harness.height = 480;
            wait(250);
            const point = field.mapToItem(screen, 0, 0);
            verify(point.x >= 0);
            verify(point.x + field.width <= screen.width);
            verify(point.y >= 0);
            verify(point.y + field.height <= screen.height);
            harness.width = 800;
            harness.height = 600;
        }
    }
}
