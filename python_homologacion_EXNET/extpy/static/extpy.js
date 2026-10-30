/*
 * ExtPy client runtime: réplica mínima del runtime de cliente de Ext.NET
 * (Ext.net.DirectEvent / App.direct / registro de componentes en App.*).
 */
(function () {
    var App = window.App = window.App || {};
    App.direct = App.direct || {};

    var completeListeners = [];

    var ExtPy = window.ExtPy = {
        baseUrl: '',
        durationMessages: [],
        // Equivale a Ext.net.DirectEvent.forbidDurationMessages
        forbidDurationMessages: false,

        boot: function (cfg) {
            ExtPy.baseUrl = cfg.baseUrl || '';
            ExtPy.durationMessages = cfg.durationMessages || [];

            // Ext.NET publica cada componente con id explícito como App.<id>
            var register = Ext.ComponentManager.register;
            Ext.ComponentManager.register = function (cmp) {
                register.apply(this, arguments);
                var id = cmp.initialConfig && cmp.initialConfig.id;
                if (id) {
                    App[id] = cmp;
                }
            };
        },

        // Equivale a Ext.net.DirectEvent.on({ ajaxrequestcomplete: fn })
        onRequestComplete: function (fn) {
            completeListeners.push(fn);
        },

        showMask: function (eventMask) {
            var messages = (eventMask && eventMask.durationMessages) || ExtPy.durationMessages,
                useMessages = messages.length > 0 && !ExtPy.forbidDurationMessages;

            if (!eventMask && !useMessages) {
                return null;
            }

            var body = Ext.getBody(),
                timers = [];

            body.mask((eventMask && eventMask.msg) || 'Working...');

            if (useMessages) {
                Ext.Array.each(messages, function (m) {
                    timers.push(setTimeout(function () {
                        body.unmask();
                        body.mask(m.message);
                    }, m.duration));
                });
            }

            return { body: body, timers: timers };
        },

        hideMask: function (mask) {
            if (mask) {
                Ext.Array.each(mask.timers, clearTimeout);
                mask.body.unmask();
            }
        },

        // Núcleo de DirectMethods y DirectEvents
        request: function (handler, params, opts) {
            opts = opts || {};

            if (opts.confirmation && !window.confirm(opts.confirmation.message || opts.confirmation)) {
                return;
            }

            var mask = ExtPy.showMask(opts.eventMask);

            Ext.Ajax.request({
                url: ExtPy.baseUrl + '/direct/' + handler,
                method: 'POST',
                jsonData: params || {},
                callback: function (options, ok, response) {
                    ExtPy.hideMask(mask);

                    if (!ok) {
                        Ext.Msg.alert('Error ' + response.status, response.responseText || response.statusText);
                        if (opts.failure) { opts.failure(response); }
                        return;
                    }

                    var result = Ext.decode(response.responseText, true) || {};

                    if (result.script) {
                        (new Function(result.script))();
                    }

                    if (opts.success) { opts.success(result.result); }

                    Ext.Array.each(completeListeners, function (fn) { fn(response, result); });
                }
            });
        }
    };
}());
