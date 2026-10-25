# SPDX-License-Identifier: GPL-2.0-or-later

"""Keep the Arduino App alive after it provisions the matrix sketch.

The host-side service owns all drawing. Keeping this component idle avoids
competing writers while retaining Arduino App CLI's supported sketch lifecycle.
"""

from arduino.app_utils import App


App.run()
