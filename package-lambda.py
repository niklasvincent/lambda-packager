#!/usr/bin/env python
from __future__ import print_function

import argparse
import logging
import os
import sys
import zipfile


from collections import namedtuple
from subprocess import Popen, PIPE


File = namedtuple("File", ["absolutePath", "relativePath"])


class Git(object):

    @staticmethod
    def executeInDirectory(directory, cmd):
        """Execute command in directory and return output"""
        current_working_directory = os.getcwd()
        os.chdir(directory)
        proc = Popen(cmd, stdout=PIPE)
        (stdout, stderr) = proc.communicate()
        os.chdir(current_working_directory)
        return (stdout, stderr)

    @staticmethod
    def getChecksum(directory):
        """Get Git commit SHA for current directory"""
        cmd = ['git', 'show-ref']
        stdout, stderr = Git.executeInDirectory(directory, cmd)
        for row in stdout.split('\n'):
            if row.find('HEAD') != -1:
                hash = row.split()[0]
                break
        return hash

    @staticmethod
    def getUncommitedChanges(directory):
        """Return uncommitted changes"""
        cmd = ['git', 'status', '-s']
        stdout, stderr = Git.executeInDirectory(directory, cmd)
        return stdout.split('\n')


class Packager(object):

    @staticmethod
    def getDeduplicatedFileList(path, exclude=None):
        """Construct recursive list of files in path"""
        return list(Packager.deduplicateFileList(
            Packager.getFileList(path, exclude)
        ))

    @staticmethod
    def getFileList(path, exclude=None):
        """Construct recursive list of files in path"""
        logging.debug("Looking for files in directory %s", path)
        f = set()
        l = len(path)
        for root, dirs, files in os.walk(path):
            for candidate_file in files:
                absolute_path = os.path.join(root, candidate_file)
                relative_path = absolute_path[l+1:]
                file = File(absolute_path, relative_path)
                if not Packager.shouldExclude(file, exclude):
                    f.add(file)
        return f

    @staticmethod
    def shouldExclude(file, exclude=None):
        """Determine if file should be excluded"""
        if not exclude:
            return False
        for pattern in exclude:
            if file.relativePath.startswith(pattern):
                return True

    @staticmethod
    def deduplicateFileList(file_list):
        """Deduplicate file list"""
        duplicated_files = set()
        for file in file_list:
            if file.relativePath.endswith(".pyc"):
                uncompiled_file = File(
                    file.absolutePath[:-1],
                    file.relativePath[:-1]
                )
                if uncompiled_file in file_list:
                    duplicated_files.add(file)
        return file_list - duplicated_files

    @staticmethod
    def createZip(filename, file_list):
        """Create zip with specified filename containing files in list"""
        zipf = zipfile.ZipFile(filename, 'w')
        for full_path, relative_path in file_list:
            zipf.write(full_path, relative_path)


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--strict",
        help="Disallow packaging if there are uncommitted Git changes",
        action="store_true"
    )
    parser.add_argument(
        "--debug",
        help="Increase output verbosity",
        action="store_true"
    )
    parser.add_argument(
        "--source",
        help="Source directory of the Lambda code",
        required=True
    )
    parser.add_argument(
        "--libraries",
        nargs="*",
        dest="libraries",
        required=False
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        dest="exclude",
        help="Directories to exclude",
        required=False
    )
    return parser


def setup_logging(debug=False):
    """Set up logging"""
    root = logging.getLogger()
    ch = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    root.addHandler(ch)
    if debug:
        ch.setLevel(logging.DEBUG)
        root.setLevel(logging.DEBUG)
    else:
        ch.setLevel(logging.INFO)
        root.setLevel(logging.INFO)


def files_to_package(sources, libraries=list(), exclude=list()):
    """Determine which files to package"""
    source_directory = os.path.abspath(sources)
    if not os.path.exists(source_directory):
        logging.error("No such source directory: %s", source_directory)
        sys.exit(1)

    source_files = Packager.getDeduplicatedFileList(
        source_directory, exclude=exclude
    )

    library_files = []
    if libraries:
        library_directories = [os.path.abspath(d) for d in libraries]
        for library_directory in library_directories:
            library_files += Packager.getDeduplicatedFileList(
                library_directory, exclude=exclude
            )

    return source_files + library_files


def zip_filename(source_directory):
    """Construct ZIP archive filename"""
    git_checksum = Git.getChecksum(source_directory)
    zip_filename = "%s-%s.zip" % (
        os.path.basename(source_directory),
        Git.getChecksum(source_directory)
    )
    return zip_filename


def enforce_strict(directory):
    """Exit if there are uncommitted changes in directory"""
    changes = Git.getUncommitedChanges(directory)
    if len(changes) > 0:
        print("Error: Refusing to package %s" % directory)
        print("There are uncommited changes:")
        for change in changes:
            print(change)
        print("Please commit changes and run again, or disable strict mode.")
        sys.exit(2)


def package(strict, sources, libraries=list(), exclude=list()):
    """Package Lambda from sources and libraries"""
    if strict:
        enforce_strict(sources)
    files = files_to_package(sources, libraries, exclude)
    output_filename = zip_filename(sources)
    Packager.createZip(output_filename, files)
    print("Created lambda zip file: %s" % output_filename)


def main():
    # Parse arguments
    args_parser = parse_arguments()
    args = args_parser.parse_args()

    # Set up logging
    setup_logging(args.debug)

    # Package Lambda
    package(args.strict, args.source, args.libraries, args.exclude)


if __name__ == '__main__':
    main()
