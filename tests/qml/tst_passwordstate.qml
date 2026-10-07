import QtQuick
import QtTest
import "../../config/plasma/shells/io.github.doview.dotfiles.lockscreen/contents/lockscreen" as Managed

TestCase {
    name: "LockScreenAuthentication"

    property QtObject backend: QtObject {
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

    SignalSpy {
        id: success
        target: Managed.PasswordState
        signalName: "authenticated"
    }

    function initTestCase() {
        Managed.PasswordState.initialize(backend);
    }

    function init() {
        Managed.PasswordState.retryTimer.stop();
        Managed.PasswordState.clear();
        Managed.PasswordState.submitting = false;
        Managed.PasswordState.promptReady = false;
        Managed.PasswordState.message = "";
        Managed.PasswordState.retryNotBefore = 0;
        backend.responses = [];
        success.clear();
    }

    function test_initialize_once() {
        Managed.PasswordState.initialize(backend);
        compare(backend.starts, 1);
    }

    function test_success_clears_pending_retry_and_all_secrets() {
        backend.failed(0);
        Managed.PasswordState.password = "test-secret";
        Managed.PasswordState.submit();
        verify(Managed.PasswordState.queued);
        backend.succeeded();
        compare(success.count, 1);
        compare(Managed.PasswordState.password, "");
        compare(Managed.PasswordState.queuedPassword, "");
        verify(!Managed.PasswordState.submitting);
        verify(!Managed.PasswordState.promptReady);
        verify(!Managed.PasswordState.retryTimer.running);
        compare(Managed.PasswordState.message, "");
    }

    function test_clear_inflight_does_not_enable_another_response() {
        backend.promptForSecretChanged();
        Managed.PasswordState.password = "first";
        Managed.PasswordState.submit();
        Managed.PasswordState.clear();
        Managed.PasswordState.password = "duplicate";
        Managed.PasswordState.submit();
        compare(backend.responses.length, 1);
        verify(Managed.PasswordState.submitting);
    }
}
