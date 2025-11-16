sysconfdir		?= /etc
apachedir		?= $(sysconfdir)/apache2
apacheconf		?= $(apachedir)/conf-available
sharedir		?= /usr/share/asl3-appliance/apache2

APACHE2_CONF = nocache.conf
APACHE2_INSTALLABLES = $(patsubst %, $(DESTDIR)$(apacheconf)/%, $(APACHE2_CONF)) 

SHARES = 000-default.conf \
	apply-apache-conf \
	default-ssl.conf
SHARES_INSTALLABLES = $(patsubst %, $(DESTDIR)$(sharedir)/%, $(SHARES))

INSTALLABLES = $(APACHE2_INSTALLABLES) $(SHARES_INSTALLABLES)

.PHONY:	install
install:	$(INSTALLABLES)

$(DESTDIR)$(apacheconf)/%:	%
	mkdir -p $(DESTDIR)$(apacheconf)
	install -m 0644  $< $@

$(DESTDIR)$(sharedir)/apply-apache-conf:  apply-apache-conf
	mkdir -p $(DESTDIR)$(sharedir)
	install -m 0755  $< $@

$(DESTDIR)$(sharedir)/%:  %
	mkdir -p $(DESTDIR)$(sharedir)
	install -m 0644  $< $@

