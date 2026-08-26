# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
FreeBSD man pages scraper.

Scrapes man pages from man.freebsd.org for BSD commands shared with macOS.
Licensed under the FreeBSD Documentation License (redistribution permitted
with copyright notice).

Many macOS commands derive from FreeBSD, so FreeBSD man pages provide
authoritative reference for shared BSD utilities.
"""

import logging
import json
import re
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class FreeBSDManPagesScraper(BaseScraper):
    """
    Scrape man pages from man.freebsd.org.

    Sources:
    - https://man.freebsd.org/cgi/man.cgi
    - License: FreeBSD Documentation License
    """

    MAN_BASE = "https://man.freebsd.org/cgi/man.cgi"

    # Key BSD commands shared with macOS - focus on system administration
    TARGET_COMMANDS = [
        # User commands (section 1)
        ("cat", 1), ("chmod", 1), ("cp", 1), ("cut", 1), ("date", 1),
        ("dd", 1), ("df", 1), ("diff", 1), ("du", 1), ("echo", 1),
        ("find", 1), ("grep", 1), ("gzip", 1), ("head", 1), ("hostname", 1),
        ("kill", 1), ("less", 1), ("ln", 1), ("ls", 1), ("mkdir", 1),
        ("mv", 1), ("nice", 1), ("nohup", 1), ("printf", 1), ("ps", 1),
        ("pwd", 1), ("rm", 1), ("rmdir", 1), ("sed", 1), ("sh", 1),
        ("sleep", 1), ("sort", 1), ("tail", 1), ("tar", 1), ("tee", 1),
        ("test", 1), ("touch", 1), ("tr", 1), ("uname", 1), ("uniq", 1),
        ("wc", 1), ("who", 1), ("whoami", 1), ("xargs", 1),
        # System admin (section 8)
        ("chown", 8), ("chgrp", 8), ("cron", 8), ("crontab", 1),
        ("dump", 8), ("fdisk", 8), ("fsck", 8), ("gpart", 8),
        ("halt", 8), ("ifconfig", 8), ("inetd", 8), ("init", 8),
        ("mount", 8), ("newfs", 8), ("ping", 8), ("reboot", 8),
        ("restore", 8), ("route", 8), ("shutdown", 8), ("swapon", 8),
        ("sysctl", 8), ("traceroute", 8), ("umount", 8), ("vipw", 8),
        ("adjkerntz", 8), ("amd", 8), ("arp", 8), ("atm", 8),
        ("boot0cfg", 8), ("bsdinstall", 8), ("bsdlabel", 8),
        ("camcontrol", 8), ("ccdconfig", 8), ("chkgrp", 8),
        ("clear", 1), ("conscontrol", 8), ("crashinfo", 8),
        ("devd", 8), ("devfs", 8), ("dhclient", 8), ("dmesg", 8),
        ("dumpfs", 8), ("fastboot", 8), ("fasthalt", 8),
        ("fbtab", 5), ("fifolog_create", 8), ("forwarding", 8),
        ("fstab", 5), ("ftpchroot", 5), ("gbde", 8), ("geom", 8),
        ("growfs", 8), ("hastctl", 8), ("hastd", 8), ("hostapd", 8),
        ("ifmib", 3), ("inetd.conf", 5), ("ipfw", 8), ("jail", 8),
        ("jexec", 8), ("jls", 8), ("kldload", 8), ("kldstat", 8),
        ("kldunload", 8), ("ldconfig", 8), ("mailwrapper", 8),
        ("mdconfig", 8), ("mdmfs", 8), ("mfiutil", 8), ("mixer", 8),
        ("mld6query", 8), ("mountd", 8), ("moused", 8), ("mptutil", 8),
        ("natd", 8), ("netstat", 1), ("newsyslog", 8), ("nfsd", 8),
        ("nfsuserd", 8), ("nologin", 8), ("nscd", 8), ("ntpdate", 8),
        ("ntpd", 8), ("ntpdc", 8), ("nvmecontrol", 8), ("pam", 8),
        ("pccardc", 8), ("pccardd", 8), ("periodic", 8), ("pkg", 8),
        ("pkg_add", 1), ("pkg_create", 1), ("pkg_delete", 1), ("pkg_info", 1),
        ("ports", 7), ("ppp", 8), ("praliases", 8), ("pw", 8),
        ("pwd_mkdb", 8), ("quotacheck", 8), ("quotaon", 8), ("rarpd", 8),
        ("rctl", 8), ("repquota", 8), ("resolvconf", 8), ("rndcontrol", 8),
        ("rpcbind", 8), ("rrenumd", 8), ("rtadvd", 8), ("rtprio", 1),
        ("rtsold", 8), ("rwhod", 8), ("sa", 8), ("savecore", 8),
        ("sconfig", 8), ("service", 8), ("setfib", 1), ("sicontrol", 8),
        ("sliplogin", 8), ("slstat", 8), ("sndstat", 8), ("sshd", 8),
        ("swapinfo", 8), ("syslogd", 8), ("systat", 1), ("tcpdump", 1),
        ("timed", 8), ("timedc", 8), ("traceroute6", 8), ("tunefs", 8),
        ("ugidfw", 8), ("uhsoctl", 8), ("usbconfig", 8), ("vidcontrol", 1),
        ("vmstat", 8), ("watch", 8), ("wlandebug", 8), ("wpa_supplicant", 8),
        ("ypbind", 8), ("ypinit", 8), ("yppoll", 8), ("yppush", 8),
        ("ypserv", 8), ("ypset", 8), ("ypxfr", 8), ("zfs", 8),
        ("zpool", 8), ("zzz", 8),
        # Library functions (section 3)
        ("queue", 3), ("bitstring", 3), ("tree", 3),
        # File formats (section 5)
        ("fstab", 5), ("group", 5), ("hosts", 5), ("passwd", 5),
        ("protocols", 5), ("services", 5), ("shells", 5), ("syslog.conf", 5),
        ("crontab", 5), ("ttys", 5), ("login.conf", 5), ("nsswitch.conf", 5),
        # Misc (section 7)
        ("hier", 7), ("hostname", 7), ("ports", 7), ("security", 7),
        ("tuning", 7), ("ordering", 7),
    ]

    def __init__(self, config: ScraperConfig):
        super().__init__(config)

    def get_source_name(self) -> str:
        return 'freebsd-man-pages'

    def scrape(self) -> List[ScrapedDocument]:
        """Scrape FreeBSD man pages."""
        documents = []

        # Deduplicate commands (some appear in multiple sections)
        seen = set()
        commands = []
        for name, section in self.TARGET_COMMANDS:
            key = f"{name}.{section}"
            if key not in seen:
                seen.add(key)
                commands.append((name, section))

        logger.info(f"Scraping {len(commands)} FreeBSD man pages...")

        for name, section in commands:
            url = f"{self.MAN_BASE}?query={name}&sektion={section}&manpath=freebsd-release"

            try:
                html = self.fetch_url(url)
                if html is None:
                    continue

                content = self._extract_content(html)

                if content and len(content) > 100:
                    doc_id = f"freebsd-man-{name}-{section}"

                    documents.append(ScrapedDocument(
                        id=doc_id,
                        url=url,
                        title=f"FreeBSD: {name}({section})",
                        content=content,
                        source="freebsd-man-pages",
                        category=self._determine_category(section),
                        tags=["freebsd", "bsd", "macos", "man_page", name, f"section{section}"],
                        scraped_at=datetime.utcnow().isoformat(),
                        metadata={
                            "platform": "bsd",
                            "command": name,
                            "section": section,
                            "doc_type": "man_page",
                            "license": "FreeBSD Documentation License",
                        }
                    ))
                    logger.debug(f"Scraped: {name}({section})")
                else:
                    logger.warning(f"Insufficient content for {name}({section})")

            except Exception as e:
                logger.warning(f"Failed to scrape {name}({section}): {e}")

        logger.info(f"Total FreeBSD man pages: {len(documents)}")
        return documents

    def _extract_content(self, html: str) -> str:
        """Extract man page content from FreeBSD man.cgi HTML."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # man.cgi wraps content in <pre> tags
            pre = soup.find('pre')
            if pre:
                # Clean up HTML entities and formatting
                text = pre.get_text(separator='\n', strip=True)
                # Remove excessive blank lines
                text = re.sub(r'\n{3,}', '\n\n', text)
                return text.strip()

            # Fallback: look for the content div
            content_div = soup.find('div', class_='man-page') or soup.find('body')
            if content_div:
                for tag in content_div.find_all(['script', 'style', 'nav', 'header', 'footer']):
                    tag.decompose()
                text = content_div.get_text(separator='\n', strip=True)
                text = re.sub(r'\n{3,}', '\n\n', text)
                return text.strip()

            return ""
        except Exception as e:
            logger.debug(f"Failed to extract content: {e}")
            return ""

    def _determine_category(self, section: str) -> str:
        """Determine category from man page section."""
        section_categories = {
            '1': 'user_commands',
            '2': 'system_calls',
            '3': 'library_functions',
            '4': 'devices',
            '5': 'file_formats',
            '6': 'games',
            '7': 'misc',
            '8': 'system_admin',
            '9': 'kernel',
        }
        base_section = str(section).rstrip('abcdefghijklmnopqrstuvwxyz')
        return section_categories.get(base_section, 'general')


def main():
    """CLI entry point for FreeBSD man pages scraper."""
    import argparse

    parser = argparse.ArgumentParser(description="Scrape FreeBSD man pages")
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--rate-limit', type=float, default=1.0)

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    config = ScraperConfig(
        output_dir=args.output_dir,
        rate_limit_delay=args.rate_limit,
    )

    scraper = FreeBSDManPagesScraper(config)
    documents = scraper.scrape()

    output_file = args.output_dir / "freebsd_man_pages.jsonl"
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        for doc in documents:
            f.write(json.dumps(doc.to_dict()) + '\n')

    print(f"Saved {len(documents)} documents to {output_file}")


if __name__ == '__main__':
    main()
