prefix			?= /usr
sysconfdir		?= /etc
firewallddir	?= $(sysconfdir)/firewalld
firewall_svcs	?= $(firewallddir)/services
# A package default, not a conffile: firewalld rewrites its own copy in
# /etc/firewalld/zones whenever the zone's permanent config changes.
firewall_zones	?= $(prefix)/lib/firewalld/zones

FIREWALLD_SERVICES = $(wildcard services/*.xml)
FIREWALLD_ZONES = $(wildcard zones/*.xml)

FIREWALLD_INSTALLABLES = $(patsubst services/%, $(DESTDIR)$(firewall_svcs)/%, $(FIREWALLD_SERVICES)) $(patsubst zones/%, $(DESTDIR)$(firewall_zones)/%, $(FIREWALLD_ZONES))

INSTALLABLES = $(FIREWALLD_INSTALLABLES) 

.PHONY:	install
install:	$(INSTALLABLES)

$(DESTDIR)$(firewall_svcs)/%:	services/%
	install -D -m 0644  $< $@

$(DESTDIR)$(firewall_zones)/%:	zones/%
	install -D -m 0644  $< $@


