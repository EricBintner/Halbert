// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Info, Palette, Shield, ExternalLink, BookOpen } from 'lucide-react'

interface AboutTabProps {
  onOpenComponentLibrary: () => void
  onOpenLegalNotices: () => void
}

/** The About tab: version, developer tools, legal notices, and links. */
export function AboutTab({ onOpenComponentLibrary, onOpenLegalNotices }: AboutTabProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Info className="h-5 w-5" />
          About Halbert
        </CardTitle>
        <CardDescription>
          AI-powered Linux system assistant
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-2">
          <h4 className="font-medium">Version</h4>
          <p className="text-sm text-muted-foreground">Development Build</p>
        </div>

        <div className="space-y-2">
          <h4 className="font-medium">Developer Tools</h4>
          <p className="text-sm text-muted-foreground mb-3">
            Explore the UI component library used to build Halbert.
          </p>
          <Button variant="outline" onClick={onOpenComponentLibrary}>
            <Palette className="h-4 w-4 mr-2" />
            View Component Library
          </Button>
        </div>

        <div className="space-y-2">
          <h4 className="font-medium">Legal & Third-Party Notices</h4>
          <p className="text-sm text-muted-foreground mb-3">
            Licenses and attributions for Halbert, its RAG corpus sources,
            software dependencies, and bundled foundation models.
          </p>
          <Button variant="outline" onClick={onOpenLegalNotices}>
            <Shield className="h-4 w-4 mr-2" />
            View Legal Notices
          </Button>
        </div>

        <div className="space-y-2">
          <h4 className="font-medium">Links</h4>
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" size="sm" asChild>
              <a href="https://github.com" target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-4 w-4 mr-1" />
                GitHub
              </a>
            </Button>
            <Button variant="ghost" size="sm" asChild>
              <a href="/docs" target="_blank" rel="noopener noreferrer">
                <BookOpen className="h-4 w-4 mr-1" />
                Documentation
              </a>
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}