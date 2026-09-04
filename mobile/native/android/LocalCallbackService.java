package io.tinyassets.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Bundle;
import android.os.IBinder;
import android.os.ResultReceiver;
import android.util.Log;

/**
 * Keeps the app process alive while a loopback OAuth callback is pending.
 *
 * Android 14+ freezes a cached (backgrounded) app's process about ten seconds
 * after it leaves the foreground - which is exactly where the app is while the
 * user signs in on the provider's page in the Custom Tab. The kernel still
 * accepts the provider's redirect on the listening socket, but the frozen app
 * never answers it, so Chrome reports ERR_CONNECTION_TIMED_OUT (founder phone
 * test 2026-08-21; a desktop CLI never hits this). A short-lived foreground
 * service is the platform's sanctioned way to stay unfrozen; it carries a
 * small "Finishing your sign-in" notification and is stopped the moment the
 * callback is handled or the flow ends.
 */
public class LocalCallbackService extends Service {
    static final String EXTRA_STARTUP_RECEIVER = "io.tinyassets.app.STARTUP_RECEIVER";
    static final int STARTUP_OK = 1;
    static final int STARTUP_FAILED = 2;
    static final String CHANNEL_ID = "tinyassets_signin";
    static final int NOTIFICATION_ID = 1455;
    // Hard ceiling: a sign-in never legitimately outlives this. Stops the
    // service even if the web layer forgot to (e.g. the WebView was torn down).
    static final long MAX_LIFETIME_MS = 12 * 60 * 1000L;
    private final android.os.Handler handler = new android.os.Handler(android.os.Looper.getMainLooper());
    private final Runnable selfStop = this::stopSelf;

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        ResultReceiver startup = null;
        if (intent != null) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                startup = intent.getParcelableExtra(EXTRA_STARTUP_RECEIVER, ResultReceiver.class);
            } else {
                startup = intent.getParcelableExtra(EXTRA_STARTUP_RECEIVER);
            }
        }
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && nm != null) {
            NotificationChannel ch = new NotificationChannel(
                CHANNEL_ID, "Sign-in", NotificationManager.IMPORTANCE_LOW);
            ch.setDescription("Shown only while a sign-in is being completed.");
            nm.createNotificationChannel(ch);
        }
        Notification.Builder b = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
            ? new Notification.Builder(this, CHANNEL_ID)
            : new Notification.Builder(this);
        Notification n = b
            .setContentTitle("TinyAssets")
            .setContentText("Finishing your sign-in…")
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setOngoing(true)
            .build();
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(NOTIFICATION_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
            } else {
                startForeground(NOTIFICATION_ID, n);
            }
        } catch (Throwable e) {
            Log.e("TinyAssetsSignin", "Could not promote sign-in service", e);
            if (startup != null) {
                Bundle details = new Bundle();
                details.putString("error", e.getClass().getSimpleName());
                startup.send(STARTUP_FAILED, details);
            }
            stopSelf();
            return START_NOT_STICKY;
        }
        if (startup != null) startup.send(STARTUP_OK, Bundle.EMPTY);
        handler.removeCallbacks(selfStop);
        handler.postDelayed(selfStop, MAX_LIFETIME_MS);
        return START_NOT_STICKY;
    }

    /** Android 15+ calls this when a dataSync service exhausts its budget. */
    public void onTimeout(int startId, int fgsType) {
        stopSelf();
    }

    @Override
    public void onDestroy() {
        handler.removeCallbacks(selfStop);
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
