"""
EJEMPLO 2 - Viewport + VBox + FormPanel
Original: src/Pages/samples/kitchen_sink/forms/login/index.cshtml

    <ext-viewport>
        <layout><ext-vboxLayout align="Middle" pack="Center" /></layout>
        <items>
            <ext-formPanel title="Login" width="480" frame="true" bodyPadding="18"
                           x-defaultAnchor="100%">
                <items>
                    <ext-textField allowBlank="false" fieldLabel="User ID" name="user" />
                    <ext-textField allowBlank="false" fieldLabel="Password" name="pass"
                                   inputType="Password" />
                    <ext-checkbox fieldLabel="Remember me" name="remember" />
                </items>
                <buttons><ext-button text="Login" /></buttons>
            </ext-formPanel>
        </items>
    </ext-viewport>

Notas de homologación:
  * Los enums de Ext.NET (Align.Middle, InputType.Password) pasan a minúsculas.
  * El prefijo ``x-`` de Ext.NET significa "config cruda": se pasa tal cual.
"""
from extpy import Button, Checkbox, ExtPage, FormPanel, TextField, Viewport

page = ExtPage("kitchen_sink/forms/login", "Login Form", __file__)


@page.on_get
def on_get():
    return Viewport(
        layout={"type": "vbox", "align": "middle", "pack": "center"},
        items=[
            FormPanel(
                title="Login",
                width=480,
                frame=True,
                body_padding=18,
                defaults={"anchor": "100%"},
                items=[
                    TextField(allow_blank=False, field_label="User ID", name="user"),
                    TextField(allow_blank=False, field_label="Password", name="pass", input_type="password"),
                    Checkbox(field_label="Remember me", name="remember"),
                ],
                buttons=[Button(text="Login")],
            )
        ],
    )
