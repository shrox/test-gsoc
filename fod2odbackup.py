import os
import sys
import shutil
import base64
import mimetypes
import magic

from lxml import etree
from copy import deepcopy
from zipfile import ZipFile
from StringIO import StringIO


def parse_fod(file_obj):
    fod_tree = etree.parse(file_obj)
    fod_root = fod_tree.getroot()
    fod_namespaces = fod_root.nsmap
    return (fod_root, fod_namespaces)


def decode_images_to_zip(zip_file, document, fod_namespaces, manifest):
    '''
        Args:
            param zip_file: zip file to write images to
            param document: document input, with or without images
            param fod_namespaces: all namespaces in the fod document
            param manifest: manifest instance to write to manifest.xml
    '''
    for image_number, node in enumerate(document.xpath(
            "//draw:image", namespaces=fod_namespaces)):
        binary_data = []
        binary_data.append(node.getchildren()[0].text)

        with magic.Magic(flags=magic.MAGIC_MIME_TYPE) as magic_instance:
            for data in binary_data:
                # Decode image using base64 module
                image = base64.b64decode(data)

                # Identify mime to identify extension
                mime = magic_instance.id_buffer(image)

                image_name = "Pictures/image%s%s" % (
                    image_number, mimetypes.guess_extension(mime))

                zip_file.writestr(image_name, image)

                node.attrib["{%s}href" %
                            (fod_namespaces['xlink'])] = image_name
                node.attrib["{%s}simple" %
                            (fod_namespaces['xlink'])] = "simple"
                node.attrib["{%s}show" %
                            (fod_namespaces['xlink'])] = "embed"
                node.attrib["{%s}actuate" %
                            (fod_namespaces['xlink'])] = "onLoad"

                node.remove(node.getchildren()[0])  # Delete binary data

                # Write to manifest object
                manifest.add_manifest_entry(image_name)


def split_file_to_zip(zip_file, fod_root, fod_namespaces, manifest):
    '''
        Args:
            param zip_file: zip file to write images to
            param manifest: to write file locations to manifest.xml

        FOD will be split to smaller files in accordance to their
        tags and written to zip
    '''

    tag2file = {
        'meta': ['meta'],
        'settings': ['settings'],
        'scripts': ['content'],
        'font-face-decls': ['content', 'styles'],
        'styles': ['styles'],
        'automatic-styles': ['content', 'styles'],
        'master-styles': ['styles'],
        'body': ['content'],
    }

    documents_processed = {
        'meta': etree.Element(
            ('{%s}document-%s' %
             (fod_namespaces['office'], 'meta')),
            nsmap=fod_namespaces),
        'settings': etree.Element(
            ('{%s}document-%s' %
             (fod_namespaces['office'], 'settings')),
            nsmap=fod_namespaces),
        'content': etree.Element(
            ('{%s}document-%s' %
             (fod_namespaces['office'], 'content')),
            nsmap=fod_namespaces),
        'styles': etree.Element(
            ('{%s}document-%s' %
             (fod_namespaces['office'], 'styles')),
            nsmap=fod_namespaces)
    }

    for child in fod_root:
        tag = etree.QName(child).localname
        for xml_filename in tag2file[tag]:
            document = documents_processed[xml_filename]
            document.append(deepcopy(child))

        # Specified document ends only with one of the following tags
        if tag in ['meta', 'settings', 'master-styles', 'body']:
            decode_images_to_zip(
                zip_file, document, fod_namespaces, manifest)

            document_string = etree.tostring(
                document, encoding='UTF-8', xml_declaration=True)

            zip_file.writestr("%s.xml" % (xml_filename), document_string)

            # Write to manifest object
            manifest.add_manifest_entry("%s.xml" % (xml_filename))


class Manifest(object):
    '''
        Class to handle manifest.xml in META-INF folder
    '''

    def __init__(self, fod_root, fod_namespaces, od_mimetype):
        self.od_mimetype = od_mimetype

        self.manifest_namespace = {
            "manifest": "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"}

        self.document = etree.Element(
            ("{%s}manifest" % (self.manifest_namespace["manifest"])),
            nsmap=self.manifest_namespace)
        self.document.attrib[
            "{%s}version" %
            (self.manifest_namespace["manifest"])] = fod_root.xpath(
            "//@office:version",
            namespaces=fod_namespaces)[0]

        self.add_manifest_entry('/')

    def add_manifest_entry(self, file_path):
        entry = etree.SubElement(
            self.document, "{%s}file-entry" %
            (self.manifest_namespace["manifest"]))

        entry.attrib[
            "{%s}full-path" %
            (self.manifest_namespace["manifest"])] = file_path

        file_name = os.path.basename(file_path)

        # Special case for empty file_name because type cannot be guessed
        if file_name == '':
            entry.attrib[
                "{%s}media-type" %
                (self.manifest_namespace["manifest"])] = self.od_mimetype
        else:
            entry.attrib[
                "{%s}media-type" %
                (self.manifest_namespace["manifest"])] = mimetypes.guess_type(file_name)[0]


def convert(file_obj, od_filename):
    fod_root, fod_namespaces = parse_fod(file_obj)
    output_od = StringIO()
    zip_file = ZipFile(output_od, "w")

    od_mimetype = mimetypes.guess_type(od_filename)[0]
    zip_file.writestr("mimetype", od_mimetype)

    manifest = Manifest(fod_root, fod_namespaces, od_mimetype)
    split_file_to_zip(
        zip_file, fod_root, fod_namespaces, manifest)

    manifest_string = etree.tostring(
        manifest.document,
        encoding='UTF-8',
        xml_declaration=True,)
    zip_file.writestr("META-INF/manifest.xml", manifest_string)

    zip_file.close()
    output_od.seek(0)

    return output_od


if __name__ == "__main__":
    fod_filename = sys.argv[1]
    od_filename = sys.argv[2]
    file_obj = open(fod_filename, "r")
    output_od = convert(file_obj, od_filename)

    with open("%s" % (od_filename), "wb") as od:
        shutil.copyfileobj(output_od, od)
