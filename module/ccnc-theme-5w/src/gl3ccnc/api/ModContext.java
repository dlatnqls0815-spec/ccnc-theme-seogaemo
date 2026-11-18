package gl3ccnc.api;

import java.io.File;

public final class ModContext {
    public final File dir;
    private final hmgapi.hook.ModContext host;

    public ModContext(hmgapi.hook.ModContext host) {
        this.host = host;
        dir = host.dir;
    }

    /** This instance exists for the zygote lifetime of an enabled registration. */
    public boolean enabled() {
        return true;
    }

    public void log(String message) {
        host.log(message);
    }

    public Object setting(String key) {
        return host.settingString(key, null);
    }

    public boolean settingBoolean(String key, boolean fallback) {
        return host.settingBoolean(key, fallback);
    }
}
