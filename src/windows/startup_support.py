"""Bounded retry of the idempotent relay heartbeat; never retries machine commands."""
import time


def refresh_lease(request, port, instance, pause=time.sleep):
    for attempt in range(3):
        try:
            return request(port, {'op': 'lease', 'instance': instance})
        except OSError:
            if attempt == 2:
                raise
            pause(0.25)
