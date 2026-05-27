def make_zabbix_login_js(login: str, password: str) -> str:
    """
    JS автологина Zabbix. Срабатывает только если текущая страница реально показывает форму входа.
    """
    if not login or not password:
        return ""

    safe_login = login.replace("\\", "\\\\").replace("'", "\\'")
    safe_password = password.replace("\\", "\\\\").replace("'", "\\'")

    return f"""
    (function() {{
        function visible(el) {{
            if (!el) return false;
            const style = window.getComputedStyle(el);
            return style && style.display !== 'none' && style.visibility !== 'hidden';
        }}

        function setValue(selectors, value) {{
            for (const selector of selectors) {{
                const elements = Array.from(document.querySelectorAll(selector));
                for (const el of elements) {{
                    if (!visible(el)) continue;
                    el.focus();
                    el.value = value;
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return true;
                }}
            }}
            return false;
        }}

        const hasPassword = document.querySelector(
            'input[type="password"], input[name="password"], input#password'
        );

        if (!hasPassword) return 'no-login-form';

        const userSet = setValue([
            'input[name="name"]',
            'input[name="username"]',
            'input[name="user"]',
            'input[name="login"]',
            'input#name',
            'input#username',
            'input#user',
            'input#login',
            'input[type="text"]'
        ], '{safe_login}');

        const passSet = setValue([
            'input[name="password"]',
            'input#password',
            'input[type="password"]'
        ], '{safe_password}');

        if (userSet && passSet) {{
            setTimeout(function() {{
                const button = document.querySelector(
                    'button[type="submit"], input[type="submit"], button[name="enter"], input[name="enter"], button.login-btn'
                );
                if (button) {{
                    button.click();
                    return;
                }}
                const form = document.querySelector('form');
                if (form) form.submit();
            }}, 250);
            return 'login-submitted';
        }}

        return 'login-form-found-but-not-filled';
    }})();
    """
