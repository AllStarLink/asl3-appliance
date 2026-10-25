sysconfdir		?= /etc
apachedir		?= $(sysconfdir)/apache2
apacheconf		?= $(apachedir)/conf-available
apachesites		?= $(apachedir)/sites-available

APACHE2_CONF = nocache.conf
APACHE2_INSTALLABLES = $(patsubst %, $(DESTDIR)$(apacheconf)/%, $(APACHE2_CONF))

APACHE2_SITES = 000-asl3-appliance.conf \
	000-asl3-appliance-ssl.conf
SITES_INSTALLABLES = $(patsubst %, $(DESTDIR)$(apachesites)/%, $(APACHE2_SITES))

INSTALLABLES = $(APACHE2_INSTALLABLES) $(SITES_INSTALLABLES)

.PHONY:	install
install:	$(INSTALLABLES)

$(DESTDIR)$(apacheconf)/%:	%
	mkdir -p $(DESTDIR)$(apacheconf)
	install -m 0644  $< $@

$(DESTDIR)$(apachesites)/%:	%
	mkdir -p $(DESTDIR)$(apachesites)
	install -m 0644  $< $@
