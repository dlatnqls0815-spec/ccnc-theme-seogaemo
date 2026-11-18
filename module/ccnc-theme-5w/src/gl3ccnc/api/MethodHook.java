package gl3ccnc.api;

public abstract class MethodHook {
    protected void beforeHookedMethod(Param param) throws Throwable {}

    protected void afterHookedMethod(Param param) throws Throwable {}

    public static final class Param {
        public final Object[] args;
        public final Object thisObject;
        private final hmgapi.hook.MethodHook.Param host;

        Param(hmgapi.hook.MethodHook.Param host) {
            this.host = host;
            args = host.args;
            thisObject = host.thisObject;
        }

        public void setResult(Object result) {
            host.setResult(result);
        }

        public boolean hasThrowable() {
            return host.hasThrowable();
        }
    }
}
