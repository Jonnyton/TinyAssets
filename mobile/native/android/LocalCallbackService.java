package io.tinyassets.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;

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
    static final String CHANNEL_ID = "tinyassets_signin";
    static final int NOTIFICATION_ID = 1455;

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
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
        } catch (Exception e) {
            // Without the foreground promotion the listener still runs; the
            // process may just be frozen while backgrounded (the pre-fix state).
            stopSelf();
        }
        return START_NOT_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
