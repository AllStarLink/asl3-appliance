prefix 			?= /usr
exec_prefix		?= $(prefix)
sbin_prefix		?= $(exec_prefix)/sbin

INSTALLABLES = $(DESTDIR)$(sbin_prefix)/asl3-self-signed-cert

.PHONY:	install
install:	$(INSTALLABLES)

$(DESTDIR)$(sbin_prefix)/%:	%
	install -D -m 0755  $< $@
