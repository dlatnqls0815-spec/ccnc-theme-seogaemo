package gl3ccnc.api;

import java.lang.reflect.Member;

public final class Bridge {
    private Bridge() {}

    public static void hookMethod(Member member, final MethodHook hook) {
        hmgapi.hook.Bridge.hookMethod(member, new hmgapi.hook.MethodHook() {
            @Override
            protected void beforeHookedMethod(Param param) throws Throwable {
                hook.beforeHookedMethod(new MethodHook.Param(param));
            }

            @Override
            protected void afterHookedMethod(Param param) throws Throwable {
                hook.afterHookedMethod(new MethodHook.Param(param));
            }
        });
    }
}
