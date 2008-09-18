#!/bin/sh

VERSION=$1

TARFILE=/tmp/pymagellan-$VERSION.tar.gz

tar -zcf $TARFILE --exclude "*~" --exclude "*.svn*" --exclude "./build*"\
  --exclude "*.pyc" . --transform "s,^\.,pymagellan-$VERSION,"