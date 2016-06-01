'use strict';


var $ = require('jquery');
var Cookie = require('js-cookie');
var Raven = require('raven-js');
var lodashGet = require('lodash.get');
var keenTracking = require('keen-tracking');

var KeenTracker = (function() {

    function _nowUTC() {
        var now = new Date();
        return new Date(
            now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(),
            now.getUTCHours(), now.getUTCMinutes(), now.getUTCSeconds()
        );
    }

    function _createOrUpdateKeenSession() {
        var expDate = new Date();
        var expiresInMinutes = 25;
        expDate.setTime(expDate.getTime() + (expiresInMinutes * 60 * 1000));
        var currentSessionId = Cookie.get('keenSessionId') || keenTracking.helpers.getUniqueId();
        Cookie.set('keenSessionId', currentSessionId, {expires: expDate, path: '/'});
    }

    function _getOrCreateKeenId() {
        if (!Cookie.get('keenUserId')) {
            Cookie.set('keenUserId', keenTracking.helpers.getUniqueId(), {expires: 365, path: '/'});
        }
        return Cookie.get('keenUserId');
    }


    function _defaultKeenPayload() {
        _createOrUpdateKeenSession();
        var returning = Boolean(Cookie.get('keenUserId'));

        var user = window.contextVars.currentUser;
        var node = window.contextVars.node;
        return {
            page: {
                title: document.title,
                url: document.URL,
                info: {},
            },
            referrer: {
                url: document.referrer,
                info: {},
            },
            tech: {
                browser: keenTracking.helpers.getBrowserProfile(),
                ua: '${keen.user_agent}',
                info: {},
            },
            time: {
                local: keenTracking.helpers.getDatetimeIndex(),
                utc: keenTracking.helpers.getDatetimeIndex(_nowUTC()),
            },
            visitor: {
                id: _getOrCreateKeenId(),
                // time_on_page: sessionTimer.value(),
                session: Cookie.get('keenSessionId'),
                returning: returning,
            },
            node: {
                id: lodashGet(node, 'id'),
                title: lodashGet(node, 'title'),
                type: lodashGet(node, 'category'),
                tags: lodashGet(node, 'tags'),
            },
            user: {
                entryPoint: user.entryPoint,
            },
            geo: {},
            anon: {
                id: user.anon.id,
                continent: user.anon.continent,
                country: user.anon.country,
                latitude: user.anon.latitude,
                longitude: user.anon.longitude,
            },
            keen: {
                addons: [
                    {
                        name: 'keen:ua_parser',
                        input: {
                            ua_string: 'tech.ua'
                        },
                        output: 'tech.info',
                    },
                    {
                        name: 'keen:url_parser',
                        input: {
                            url: 'page.url',
                        },
                        output: 'page.info',
                    },
                    {
                        name: 'keen:url_parser',
                        input: {
                            url: 'referrer.url',
                        },
                        output: 'referrer.info',
                    },
                    {
                        name: 'keen:referrer_parser',
                        input: {
                            referrer_url: 'referrer.url',
                            page_url: 'page.url',
                        },
                        output: 'referrer.info',
                    },
                ]
            },
        };
    }  // end _defaultKeenPayload

    function _trackCustomEvent(client, collection, eventData) {
        client.recordEvent(collection, eventData, function (err) {
            if (err) {
                Raven.captureMessage('Error sending Keen data to ' + collection + ': <' + err + '>', {
                    extra: {payload: eventData}
                });
            }
        });
    }

    function _trackCustomEvents(client, events) {
        client.recordEvents(events, function (err, res) {
            if (err) {
                Raven.captureMessage('Error sending Keen data for multiple events: <' + err + '>', {
                    extra: {payload: events}
                });
            } else {
                for (var collection in res) {
                    var results = res[collection];
                    for (var idx in results) {
                        if (!results[idx].success) {
                            Raven.captureMessage('Error sending Keen data to ' + collection + '.', {
                                extra: {payload: events[collection][idx]}
                            });
                        }
                    }
                }
            }
        });
    }

    function KeenTracker() {
        if (instance) {
            throw new Error('Cannot instantiate another KeenTracker instance.');
        } else {
            var self = this;

            self._publicClient = null;
            self._privateClient = null;

            self.init = function _initKeentracker(params) {
                var self = this;

                self._publicClient = new keenTracking({
                    projectId: params.public.projectId,
                    writeKey: params.public.writeKey,
                });
                self._publicClient.extendEvents(_defaultPublicKeenPayload);

                self._privateClient = new keenTracking({
                    projectId: params.private.projectId,
                    writeKey: params.private.writeKey,
                });
                self._privateClient.extendEvents(_defaultPrivateKeenPayload);

                return self;
            };

            var _defaultPublicKeenPayload = function() { return _defaultKeenPayload(); };
            var _defaultPrivateKeenPayload = function() {
                var payload = _defaultKeenPayload();
                var user = window.contextVars.currentUser;
                payload.tech.ip = '${keen.ip}';
                payload.user.id = user.id;
                payload.user.locale = user.locale;
                payload.user.timezone = user.timezone;
                payload.keen.addons.push({
                    name: 'keen:ip_to_geo',
                    input: {
                        ip: 'tech.ip',
                    },
                    output: 'geo',
                });

                return payload;
            };

            self.trackPageView = function () {
                var self = this;
                self.trackPublicEvent('pageviews', {});
                self.trackPrivateEvent('pageviews', {});
            };

            self.trackPrivateEvent = function(collection, event) {
                return _trackCustomEvent(self._privateClient, collection, event);
            };
            self.trackPrivateEvents = function(events) {
                return _trackCustomEvents(self._privateClient, events);
            };

            self.trackPublicEvent = function(collection, event) {
                return _trackCustomEvent(self._publicClient, collection, event);
            };
            self.trackPublicEvents = function(events) {
                return _trackCustomEvents(self._publicClient, events);
            };
        }
    }

    var instance = null;
    return {
        getInstance: function(keenParams) {
            if (!instance) {
                console.log('In builder, contextvars is:', window.contextVars);
                instance = new KeenTracker();
                instance.init(window.contextVars.keen);
            }
            return instance;
        }
    };
})();

module.exports = KeenTracker;
