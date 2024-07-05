# Copyright 2024 ROOD, Socialistische Jongeren
# Distributed under the terms of the EUPL v1.2
#
# This doesn't really do anything since the dev environment will
# require additional steps to setup anyway. But it makes dependency
# management a lot easier.

EAPI=8

DISTUTILS_USE_PEP517=setuptools
PYTHON_COMPAT=( python3_{10..13} )

inherit distutils-r1 git-r3

DESCRIPTION="Departure from our old symfony internal site"
HOMEPAGE="
	https://github.com/roodjong/symfexit
"
EGIT_REPO_URI="https://github.com/roodjong/symfexit.git"

LICENSE="EUPL-1.2"
SLOT="0"
KEYWORDS="~amd64"

RDEPEND="
	dev-python/django[${PYTHON_USEDEP}]
	dev-python/django-constance[${PYTHON_USEDEP}]
	dev-python/django-picklefield[${PYTHON_USEDEP}]
	dev-python/django-tailwind[${PYTHON_USEDEP}]
	dev-python/django-tinymce[${PYTHON_USEDEP}]
	dev-python/dj-database-url[${PYTHON_USEDEP}]
	dev-python/fontawesomefree[${PYTHON_USEDEP}]
	dev-python/hashids[${PYTHON_USEDEP}]
	dev-python/mollie-api-python[${PYTHON_USEDEP}]
	dev-python/pillow[${PYTHON_USEDEP}]
	dev-python/psycopg:0[${PYTHON_USEDEP}]
"
