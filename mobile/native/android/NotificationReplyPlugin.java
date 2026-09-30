package io.tinyassets.app;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * Hands the text typed into a notification's inline Reply to the web app, once.
 *
 * MainActivity parks the reply here after checking the per-install secret; the
 * app's own page collects it and submits it through its signed-in session. The
 * text is consumed on read so it cannot be submitted twice, and it lives only
 * in memory -- a process that dies before the page collects it drops the reply
 * rather than persisting a user's words anywhere.
 */
@CapacitorPlugin(name = "NotificationReply")
public class NotificationReplyPlugin extends Plugin {
    private static String requestId;
    private static String itemId;
    private static String text;

    static synchronized void park(String request, String item, String reply) {
        requestId = request;
        itemId = item;
        text = reply;
    }

    @PluginMethod
    public void consume(PluginCall call) {
        JSObject result = new JSObject();
        synchronized (NotificationReplyPlugin.class) {
            if (requestId != null && text != null) {
                result.put("request_id", requestId);
                if (itemId != null) result.put("item_id", itemId);
                result.put("text", text);
            }
            requestId = null;
            itemId = null;
            text = null;
        }
        call.resolve(result);
    }
}
