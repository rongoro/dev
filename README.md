== Dev ==

The goal of this tool is to provide a development environment for projects or organizations
that allow for the integration of a diverse set of packages. This may include packages with different
development and build models. The requirement is to achieve completeness and reproduciblity
regardless of what tools the software packages happen to use.

One version of such a system would be the monorepo used inside Google that is
managed by bazel and stored in their custom source control system, Piper. Unfortunately
other companies don't have access to such systems and more importantly don't have the
capacity to create custom BUILD rules to build all the third party tools they may choose to
use. Autogenerating BUILD files may help but has its own complications.

Often the easiest solution is to create a reproducible image in which a package can be built using
its own build system. This compromise means we give up on the benefits of complete dependency tracking 
but we can simulate build enviornments that might exists at third parties and we don't have to 
write our own build configurations for packages that already have their own.

=== Prerequisits ===

* Python 2.7
* docker


