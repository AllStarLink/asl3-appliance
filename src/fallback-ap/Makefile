prefix 			?= /usr
sysconfdir		?= /etc
exec_prefix		?= $(prefix)
bin_prefix		?= $(exec_prefix)/bin
cockpit_etc		?= $(sysconfdir)/cockpit
cockpit_brand	?= $(prefix)/share/cockpit/branding/debian-AllStarLink

INSTALLABLES = \
	$(DESTDIR)/lib/systemd/system/fallback-ap.service \
	$(DESTDIR)/lib/systemd/system/fallback-ap.timer \
	$(DESTDIR)/etc/default/fallback-ap \
	$(DESTDIR)/usr/libexec/asl3/fallback-ap-watchdog.py

.PHONY:	default install

default:
	@echo $(INSTALLABLES)

install: $(INSTALLABLES)

$(DESTDIR)/etc/default/fallback-ap:	fallback-ap.default.sh
	install -D -m 0644 $< $@

$(DESTDIR)/lib/systemd/system/%:	%
	install -D -m 0644 $< $@

$(DESTDIR)$(prefix)/libexec/asl3/%:	%
	install -D -m 0755 $< $@





