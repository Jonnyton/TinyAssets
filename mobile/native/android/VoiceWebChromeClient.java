package io.tinyassets.app;

import android.Manifest;
import android.app.AlertDialog;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.webkit.PermissionRequest;
import android.webkit.WebView;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebChromeClient;

/**
 * Grants WebRTC microphone capture only to the production TinyAssets origin.
 *
 * The web app initiates capture from its record control. Android permission is
 * requested only after a second, native disclosure/continue gesture. Camera,
 * mixed-resource requests, lookalike hosts, non-default ports, and background
 * requests are denied.
 */
public final class VoiceWebChromeClient extends BridgeWebChromeClient {
    static final String TRUSTED_SCHEME = "https";
    static final String TRUSTED_HOST = "tinyassets.io";
    static final int MICROPHONE_REQUEST_CODE = 7104;

    private static final String AUDIO_CAPTURE = PermissionRequest.RESOURCE_AUDIO_CAPTURE;
    private static final String INSTALL_TRACKER = """
        (() => {
          if (location.protocol !== 'https:' || location.hostname !== 'tinyassets.io' ||
              (location.port !== '' && location.port !== '443')) return;
          const media = navigator.mediaDevices;
          if (!media || typeof media.getUserMedia !== 'function' ||
              window.__tinyAssetsVoiceStreams) return;
          const streams = new Set();
          Object.defineProperty(window, '__tinyAssetsVoiceStreams', { value: streams });
          const original = media.getUserMedia.bind(media);
          media.getUserMedia = (constraints) => original(constraints).then((stream) => {
            if (constraints && constraints.audio) {
              streams.add(stream);
              stream.getTracks().forEach((track) =>
                track.addEventListener('ended', () => {
                  if (stream.getTracks().every((item) => item.readyState === 'ended')) {
                    streams.delete(stream);
                  }
                }, { once: true })
              );
            }
            return stream;
          });
        })();
        """;
    private static final String STOP_CAPTURE = """
        (() => {
          const streams = window.__tinyAssetsVoiceStreams;
          if (streams) {
            streams.forEach((stream) => stream.getTracks().forEach((track) => track.stop()));
            streams.clear();
          }
          window.dispatchEvent(new CustomEvent('tinyassets:native-microphone-stopped'));
        })();
        """;

    private final AppCompatActivity activity;
    private final Bridge bridge;
    private PermissionRequest pendingRequest;

    public VoiceWebChromeClient(Bridge bridge, AppCompatActivity activity) {
        super(bridge);
        this.activity = activity;
        this.bridge = bridge;
    }

    static boolean isTrustedOrigin(Uri origin) {
        if (origin == null
                || !TRUSTED_SCHEME.equals(origin.getScheme())
                || !TRUSTED_HOST.equals(origin.getHost())
                || origin.getUserInfo() != null) {
            return false;
        }
        int port = origin.getPort();
        return port == -1 || port == 443;
    }

    private static boolean isAudioOnly(PermissionRequest request) {
        String[] resources = request.getResources();
        return resources.length == 1 && AUDIO_CAPTURE.equals(resources[0]);
    }

    public static void installMediaTracker(WebView webView) {
        Uri current = Uri.parse(webView.getUrl() == null ? "" : webView.getUrl());
        if (isTrustedOrigin(current)) {
            webView.evaluateJavascript(INSTALL_TRACKER, null);
        }
    }

    @Override
    public void onPermissionRequest(PermissionRequest request) {
        activity.runOnUiThread(() -> handlePermissionRequest(request));
    }

    private void handlePermissionRequest(PermissionRequest request) {
        if (!isTrustedOrigin(request.getOrigin())
                || !isAudioOnly(request)
                || !activity.hasWindowFocus()
                || activity.isFinishing()) {
            request.deny();
            return;
        }
        if (pendingRequest != null) {
            pendingRequest.deny();
        }
        pendingRequest = request;
        installMediaTracker(requestingWebView());

        new AlertDialog.Builder(activity)
            .setTitle("Use your microphone?")
            .setMessage(
                "TinyAssets will listen only while you record a voice message. "
                    + "Recording stops when you leave the app."
            )
            .setPositiveButton("Continue", (dialog, which) -> continueAfterDisclosure())
            .setNegativeButton("Not now", (dialog, which) -> denyPending())
            .setOnCancelListener(dialog -> denyPending())
            .show();
    }

    private void continueAfterDisclosure() {
        if (ContextCompat.checkSelfPermission(activity, Manifest.permission.RECORD_AUDIO)
                == PackageManager.PERMISSION_GRANTED) {
            grantPending();
            return;
        }
        ActivityCompat.requestPermissions(
            activity,
            new String[] { Manifest.permission.RECORD_AUDIO },
            MICROPHONE_REQUEST_CODE
        );
    }

    private WebView requestingWebView() {
        return bridge.getWebView();
    }

    public boolean onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        if (requestCode != MICROPHONE_REQUEST_CODE) {
            return false;
        }
        boolean granted = permissions.length == 1
            && Manifest.permission.RECORD_AUDIO.equals(permissions[0])
            && results.length == 1
            && results[0] == PackageManager.PERMISSION_GRANTED;
        if (granted) {
            grantPending();
        } else {
            denyPending();
        }
        return true;
    }

    private void grantPending() {
        if (pendingRequest != null && isTrustedOrigin(pendingRequest.getOrigin())) {
            pendingRequest.grant(new String[] { AUDIO_CAPTURE });
            pendingRequest = null;
        }
    }

    private void denyPending() {
        if (pendingRequest != null) {
            pendingRequest.deny();
            pendingRequest = null;
        }
    }

    public void stopCapture(WebView webView) {
        Uri current = Uri.parse(webView.getUrl() == null ? "" : webView.getUrl());
        if (isTrustedOrigin(current)) {
            webView.evaluateJavascript(STOP_CAPTURE, null);
        }
    }

    public void stopCaptureAndDeny(WebView webView) {
        denyPending();
        stopCapture(webView);
    }
}
