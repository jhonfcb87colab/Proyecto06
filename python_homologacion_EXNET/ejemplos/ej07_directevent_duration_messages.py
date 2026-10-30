"""
EJEMPLO 7 - DirectEvents, EventMask y mensajes por duración
Original: src/Pages/samples/events/directevents/duration_messages/

    <ext-resourcemanager>
        <DirectEventDurationMessages>
            <ext-durationMessage Duration="1000" Message="Global duration message ..." />
        </DirectEventDurationMessages>
    </ext-resourcemanager>

    <ext-button Text="Run">
        <DirectEvents>
            <Click pageHandler="DoSomething" method="POST">
                <EventMask><ext-eventMask><DurationMessages>...</DurationMessages></ext-eventMask></EventMask>
            </Click>
        </DirectEvents>
    </ext-button>

    public IActionResult OnPostDoSomething() { Thread.Sleep(8000); return this.Direct(); }
    [Direct] public IActionResult OnPostSomeDirectMethod() { Thread.Sleep(8000); return this.Direct(); }

Homologación:
  <ext-resourcemanager> mensajes globales -> PageResult(duration_messages=[...])
  <DirectEvents><Click pageHandler=...>   -> direct_events={"click": DirectEvent(...)}
  Ext.net.DirectEvent.on(ajaxrequestcomplete) -> ExtPy.onRequestComplete(fn)
  Ext.net.DirectEvent.forbidDurationMessages  -> ExtPy.forbidDurationMessages
"""
import time

from extpy import (Button, Container, DirectEvent, DurationMessage, EventMask, ExtPage, Label,
                   Listener, PageResult)

page = ExtPage("events/directevents/duration_messages", "DirectEvent Duration Messages", __file__)

SLEEP_SECONDS = 8

HEAD = """
<script>
    Ext.onReady(function () {
        // Reemplaza el listener AjaxRequestComplete del ResourceManager
        ExtPy.onRequestComplete(function () {
            Ext.Msg.alert('Done', 'The operation has been completed.');
        });
    });
</script>"""


@page.direct_handler
def DoSomething():  # noqa: N802
    time.sleep(SLEEP_SECONDS)


@page.direct_method
def SomeDirectMethod():  # noqa: N802
    time.sleep(SLEEP_SECONDS)


def row(button, text, label_id=None):
    label = Label(min_width=450, html="&nbsp;- " + text)
    if label_id:
        label["id"] = label_id
    return Container(layout="hbox", items=[button, label])


@page.on_get
def on_get():
    specific_mask = EventMask(duration_messages=[
        DurationMessage(1000, "Hm... taking a bit longer than expected..."),
        DurationMessage(3500, "Well, this is a bit unexpected... almost there now..."),
        DurationMessage(5000, "Woah, this is embarrassing. The server is taking really long. "
                              "Sorry about this... still waiting..."),
    ])

    container = Container(
        layout="vbox",
        defaults={"margin": "0 0 7 0"},
        items=[
            row(Button(text="Run", width=75,
                       direct_events={"click": DirectEvent("DoSomething", event_mask=specific_mask)}),
                "a long running DirectEvent with specific duration messages"),
            row(Button(text="Run", width=75,
                       direct_events={"click": DirectEvent("DoSomething")}),
                "a long running DirectEvent with global duration messages"),
            row(Button(text="Run", width=75, listeners={"click": Listener("""
                    App.direct.SomeDirectMethod({
                        eventMask: {
                            durationMessages: [
                                { duration: 1000, message: 'DirectMethod duration message for 1000 milliseconds' },
                                { duration: 3000, message: 'DirectMethod duration message for 3000 milliseconds' }
                            ]
                        }
                    });""")}),
                "a long running DirectMethod with specific duration messages"),
            row(Button(text="Forbid", width=75, listeners={"click": Listener("""
                    ExtPy.forbidDurationMessages = !ExtPy.forbidDurationMessages;
                    var text = ExtPy.forbidDurationMessages ? 'Allow' : 'Forbid';
                    this.setText(text);
                    App.Label1.setHtml('&nbsp;- ' + text + ' duration messages');""")}),
                "Forbid duration messages", label_id="Label1"),
        ],
    )

    return PageResult(
        container,
        head=HEAD,
        body="<h1>DirectEvent Duration Messages</h1>",
        duration_messages=[
            DurationMessage(1000, "Global duration message for 1000 milliseconds"),
            DurationMessage(3500, "Global duration message for 3500 milliseconds"),
            DurationMessage(5000, "Global duration message for 5000 milliseconds"),
        ],
    )
